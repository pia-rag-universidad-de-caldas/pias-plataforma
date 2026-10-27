# Arquitectura actual

Cómo está armado el proyecto hoy: qué módulos hay, cómo se reparten el trabajo y qué reglas los mantienen separados.
Para cambiar algo concreto, ver [guia-ingesta.md](guia-ingesta.md), [guia-data.md](guia-data.md) y [api.md](api.md).

## El flujo de punta a punta

```
data/base/<anio>/<mes>/<semana>/<codigo>/<archivo>
        │  prueba-chunking organize            (CLI, módulo ingesta)
        ▼
data/ingesta/<categoria>/<tipo>/…  +  memoria SQLite (data/ingesta/.memoria.sqlite3)
        │  GET /ingesta/data, /ingesta/data/file, /ingesta/data/content   (HTTP)
        ▼
chunking  ── convierte con Docling y parte en chunks ──┐
        │  POST /data/batch, GET /data/nodes          │  (HTTP)
        ▼                                             │
Neo4j (módulo data): grafo PIAA de producción  +  registro de experimentos (etiquetas EXP_*)
```

1. **ingesta** recorre `data/base/`, copia (o mueve) cada archivo nuevo a `data/ingesta/`, lo clasifica (vacío,
   extraño, duplicado por hash, duplicado por código, incompleto, apto para chunking) y lleva una memoria SQLite con la
   metadata de cada archivo. Solo los **aptos para chunking** (`vigentes/`) pasan a la etapa siguiente.
2. **chunking** pide a ingesta los aptos, los convierte con Docling y los parte en chunks. Tiene dos caminos:
   - **corridas** (`/chunking/runs`, feature 023): escriben en el grafo de producción
     (`PIAA → JSON → SECCION → FRAGMENTOS`);
   - **experimentos** (`/chunking/experiments`, feature 025): convierten con una configuración, aplican un plan de
     estrategias por sección y lo registran todo con etiquetas propias (`EXPERIMENTO`, `EXP_*`), sin tocar producción.
     Es el registro que usa el laboratorio, con puntuaciones por experimento.
3. **data** es la única puerta a Neo4j: valida todo contra el esquema del grafo y lo escribe.

## Los cuatro paquetes

Todo vive en `src/`, en un solo proyecto de uv (`pyproject.toml`, `module-name = ["ingesta", "data", "chunking",
"server"]`).

| Paquete | Qué es | Guarda en | Extra de uv |
|---|---|---|---|
| `ingesta` | organiza `data/base/` → `data/ingesta/`, estadísticas, API de los aptos | SQLite (vía SQLAlchemy) y disco | — |
| `data` | CRUD del grafo PIAA y del registro de experimentos | Neo4j | `data` (driver `neo4j`) |
| `chunking` | conversión con Docling, estrategias de chunking, experimentos y puntuaciones | nada propio: todo va a `data` por HTTP | `chunk` (Docling, ~6 GB con PyTorch) |
| `server` | raíz de composición: un solo servidor HTTP que monta los otros tres | — | — |

### Regla principal: los módulos no se importan entre sí

`ingesta`, `data` y `chunking` **nunca** se importan uno a otro. Cuando uno necesita a otro, lo llama **por HTTP al
mismo servidor** (`ServerSettings.self_url`). Solo `server` los importa a todos, para montarlos. Esto lo hace cumplir
Ruff: cada módulo tiene un `ruff.toml` que extiende el `pyproject.toml` y prohíbe importar a los demás (`TID251`).

Así cada módulo se puede separar mañana en su propio servicio sin tocar su dominio: solo cambia la URL.

## Capas dentro de cada módulo

Los tres módulos siguen el mismo esquema tipo *clean architecture*. Las dependencias van siempre hacia adentro:

```
api/ (HTTP)  ─┐
cli.py        ├──►  domain/ (reglas)  ──►  models/ (datos e interfaces)  ◄──  repository/ , adapters/
              ┘                                                               (implementan las interfaces)
```

| Capa | Qué contiene | Qué NO puede hacer |
|---|---|---|
| `models/` | dataclasses congeladas e interfaces (`Protocol`/ABC), un archivo por función | importar nada de infraestructura |
| `domain/` | reglas de negocio, clases con métodos estáticos | importar el ORM, el driver, FastAPI, `httpx`, `pathlib`, ni imprimir |
| `repository/` | implementa los repositorios del dominio sobre un adaptador | escribir SQL o Cypher crudo fuera del adaptador (salvo `data`, ver abajo) |
| `adapters/` | el borde con el mundo: base de datos, disco, Neo4j, Docling, HTTP | — (es el único lugar que puede importar esas librerías) |
| `api/` | FastAPI: rutas, dependencias, esquemas de respuesta | contener reglas de negocio |
| `config/` | parámetros y rutas por defecto | — |

Qué librería puede importar quién (Ruff `TID251`, en `pyproject.toml`):

| Librería | Solo en |
|---|---|
| `sqlalchemy`, `sqlite3` | `ingesta/adapters/` (en la práctica, `sqlalchemy_converter.py`) |
| `pathlib`, `shutil`, `os`, `stat` | `ingesta/adapters/local_files.py` (y `data/adapters/environment.py` para `os`) |
| `neo4j` | `data/adapters/neo4j_adapter.py` |
| `docling`, `docling_core`, `httpx` | `chunking/adapters/` |
| `fastapi`, `starlette`, `uvicorn` | `*/api/` y `server/` |

## ingesta por dentro

```
cli.py ──► domain/ (Discovery, Organization, Classifier, Duplicates, Statistics…)
              │ usa los Protocol de models/persistence.py
              ▼
repository/ (DbFileRepository, DbCategoryRepository, DbRunRepository)
              │ sobre models.ORMAdapter
              ▼
adapters/sql_adapter.py (SQLORMAdapter: reglas del CRUD, migraciones)
              │ sobre models.SQLConverter
              ▼
adapters/sqlalchemy_converter.py (SqlAlchemyConverter: el único que habla SQL)
```

- **Las tablas se describen, no se escriben en SQL.** `tables/` define cada tabla con `TableSpec`/`ColumnSpec`. Cada
  columna se llama igual que el campo de su entidad en `models/entities.py` (en español, porque son las columnas de la
  memoria existente). El adaptador las crea (`from_scratch`) o las abre y migra (`from_existing`).
- **Migraciones por regla.** Cada `TableSpec` puede tener `needs_migration(columnas_actuales) -> bool`. Al abrir una
  memoria vieja, si la regla dice que sí, el adaptador **reconstruye** la tabla: copia las filas, la borra, la crea con
  la definición nueva y reinserta lo que coincide. Todo en una transacción: si algo falla, la memoria queda como estaba.
- **El disco también es un adaptador.** `FileAdapter` (ABC en `models/persistence.py`) trabaja con rutas relativas a una
  raíz, como texto; `LocalFileAdapter` es el único que usa `pathlib`/`shutil`. Copias atómicas (`*.parcial` y luego
  renombrar).
- **El dominio no imprime.** Informa con callbacks (`on_progress`, `on_failure`) y la CLI decide qué mostrar.
- **Clasificación con todo el corpus.** `Classifier.classify` evalúa cada categoría por separado (un archivo puede tener
  varias), elige la principal por prioridad (el orden del enum `Category`) y esa decide la carpeta en `data/ingesta/`.
  Un archivo nuevo puede desplazar a otro que era vigente; `Organization.relocate` lo mueve en la misma corrida.

## data por dentro

```
api/routes/ ──► repository/piaa_repository.py (PiaaRepository: arma el Cypher)
                    │ valida con schema/piaa_schema.py (qué relaciones existen)
                    ▼
                models.GraphAdapter ◄── adapters/neo4j_adapter.py (Neo4jGraphAdapter: el único que importa neo4j)
```

- **Qué existe en el grafo** lo dicen dos cosas: los enums `Label` y `RelationshipType` (`models/piaa.py`) y la tupla
  `RELATIONSHIPS` (`schema/piaa_schema.py`), que lista cada relación permitida con su origen y su destino. Es el
  equivalente de `ingesta/tables/`.
- **Cypher seguro.** Las etiquetas y los tipos no admiten parámetros en Cypher, así que se concatenan, pero **solo**
  valores de los enums (`_name`), nunca texto del usuario. Todo lo demás va en parámetros.
- **Nodos.** Cada nodo tiene una etiqueta, un `id` de texto único por etiqueta (restricción `piaa_id_<LABEL>`, creada al
  arrancar) y propiedades libres: valores simples o listas homogéneas, lo que Neo4j sabe guardar. Un mapa no se puede:
  se guarda como texto JSON.
- **Escritura masiva.** `POST /data/batch` escribe nodos y relaciones en **una transacción** (todo o nada). Cada nodo
  tiene un modo: `replace` (sus propiedades pasan a ser las enviadas), `ensure` (solo se crea si no existe) o `merge`
  (pone las enviadas y conserva las demás). `replace_from` borra antes los descendientes de un nodo siguiendo solo las
  relaciones de **composición** (`COMPOSITION`, junto al esquema en `schema/piaa_schema.py`; la escritura del lote es
  `repository/batch_writer.py` y su validación `schema/batch_rules.py`).

## chunking por dentro

- **Modelos** (`models/`, un archivo por función como en ingesta): `concepts.py`, `requests.py`, `results.py`,
  `queries.py`, `batch.py` (lo que se escribe en el grafo) y `stored.py`: un `TypedDict` por cada forma guardada en el
  grafo, que usan tanto el dominio al escribir como los mappers al leer, para que una propiedad mal escrita sea un
  error de mypy.
- **Puertos** (`models/ports.py`): de dónde salen los documentos (`ChunkSource`, ingesta), dónde se guardan
  (`ChunkSink`, el store de experimentos) y quién convierte (`Converter`, Docling). El dominio solo conoce los puertos.
- **Dominio** (`domain/`): `production/` (corridas 023: `Runner`, `Selection` —qué está pendiente según el
  `fingerprint` de los parámetros— y `Hierarchy`, que arma el lote para el grafo) y `experiments/` (025: `ExperimentRunner`,
  `Planner` —qué regla toma cada sección—, `Parameters`, `graph.py` —el lote del experimento—, `scoring.py` y
  `promotion.py`).
- **Adaptadores** (`adapters/`):
  - `docling_converter.py`: Docling (import diferido; sin el extra `chunk` todo lo demás funciona).
  - `strategies/`: una estrategia de chunking por archivo (`hybrid`, `element`, `section`, `page`, `fixed`, `points`,
    `semantic`), sobre el documento ya convertido.
  - `http/` (feature 026): reexporta el cliente base de `common.http` (feature 033), el único que llama a `httpx`, con
    la traducción de errores y la paginación, y tiene la sonda de salud (`probe.py`); `adapters/ingesta/` y `adapters/data/` tienen un cliente delgado por recurso y los **mappers**, el
    único lugar donde los nombres en español (columnas, propiedades del grafo) se convierten en modelos en inglés.
  - `ingesta/source.py`, `data/sink.py`, `data/experiment_store.py`: fachadas que implementan los puertos usando
    esos clientes; `session.py` las arma para una corrida.
- Las corridas y los experimentos corren **en un hilo propio**: hacen peticiones HTTP al mismo servidor, que tiene que
  seguir libre para contestarlas. Hay un solo trabajo pesado a la vez (409 si ya hay otro).

## server

`src/server/` crea una `FastAPI` raíz y **monta** (`app.mount`) la app de cada módulo bajo su prefijo: `/ingesta`,
`/data`, `/chunking`. Montar conserva los manejadores de error y el `/docs` de cada uno. Abre el adaptador de Neo4j una
vez y lo cierra al apagar; si Neo4j no está, `data` se monta igual sobre un grafo "no disponible" que responde 503. Ver
[api.md](api.md).

## Convenciones que valen para todo

- **Código en inglés; datos guardados en español.** Identificadores, docstrings, mensajes y CLI en inglés. Siguen en
  español, porque son datos ya guardados o publicados: tablas y columnas de la memoria, valores de `Category`, claves
  JSON de ingesta y del reporte, CSV, carpetas, y las etiquetas, tipos y propiedades del grafo.
- **Tipos estrictos.** mypy `strict`, sin `Any` fuera de los adaptadores, sin `dict`/`list` sin parámetros, sin
  `# type: ignore`. Datos en dataclasses `frozen=True`, no `dict` sueltos.
- **`__init__.py` reexporta lo público** y se importa por paquete con ruta absoluta (`from ingesta.domain import …`).
- **Spec Driven Development.** Antes de tocar código: `spec/constitution/` y la carpeta de la feature
  (`spec/features/NNN-*/` con `spec.md`, `plan.md`, `tasks.md`). Una feature nueva = una carpeta nueva.

## Cómo se valida un cambio

```bash
uv run ruff format && uv run ruff check   # formato y lint
uv run mypy                               # tipos (strict)
uv run pytest                             # tests de chunking (tests/), con httpx.MockTransport
```

Además, según lo que se toque:

- **ingesta:** `organize --simulate` y `GET /ingesta/stats` sobre una **copia** de la memoria, antes y después; deben
  quedar iguales salvo la fecha. Nunca sobre `data/ingesta/.memoria.sqlite3` directamente.
- **data y chunking:** Neo4j de prueba en Docker y los archivos de `http/` (ver [api.md](api.md#probar-con-los-archivos-http)).

Ojo: `uv sync` a secas desinstala el driver de Neo4j; usar `uv sync --extra data` (y `--extra chunk` solo en un
entorno aparte, porque Docling pesa ~6 GB).
