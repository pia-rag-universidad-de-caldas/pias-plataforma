# Cómo funciona la API

Un solo servidor HTTP (FastAPI + uvicorn) sirve los tres módulos, cada uno bajo su prefijo. Los módulos también usan
esta API para hablar entre ellos.

```bash
NEO4J_PASSWORD=... uv run prueba-chunking serve      # http://127.0.0.1:8000
# opciones: --host --port --base --ingest --memory --db --neo4j-url --neo4j-user --neo4j-database
```

## Estructura del servidor

```
                       http://127.0.0.1:8000
                ┌──────────────┴──────────────────────────────┐
  GET /health   │  app raíz (src/server/app.py)               │
                │   ├─ mount /ingesta  → ingesta.api.create_app│  memoria SQLite (abierta por petición)
                │   ├─ mount /data     → data.api.create_app   │  Neo4j (un adaptador para toda la app)
                │   └─ mount /chunking → chunking.api.create_app│  habla con /ingesta y /data por HTTP
                └─────────────────────────────────────────────┘
```

- **Montar** (`app.mount`) en vez de `include_router` hace que cada módulo conserve su propia app: sus manejadores de
  error, su formato de error y su documentación (`/ingesta/docs`, `/data/docs`, `/chunking/docs`).
- **`GET /health`** (raíz) consulta cada módulo en proceso y responde siempre 200, con `"status": "ok"` o `"degraded"`
  y el detalle por módulo.
- **Sin Neo4j** (falta la clave, el driver o la conexión), el servidor arranca igual: `/data` se monta sobre un grafo
  "no disponible" que responde 503 en todo, y `/ingesta` sigue funcionando.
- **Ciclo de vida:** el adaptador de Neo4j se abre una vez al arrancar y lo cierra el *lifespan* de la app raíz.
  Starlette no corre el lifespan de las sub-apps montadas, por eso lo maneja la raíz.
- Cada módulo se puede levantar solo, para pruebas: `uv run python -m ingesta serve` (rutas sin prefijo) o
  `uv run prueba-chunking-data serve` (puerto 8001).

## Errores

| Módulo | Cuerpo del error | Errores propios |
|---|---|---|
| ingesta | `{"detalle": "..."}` | memoria inaccesible → 503; error de disco → 500 |
| data | `{"detail": "..."}` | Neo4j caído o consulta rechazada → 503 |
| chunking | `{"detail": "..."}` | ingesta o data no responden → 503; Docling no instalado → 503; ya hay un trabajo pesado corriendo → 409 |

En los tres, un cuerpo o un parámetro inválido da **422** con el formato de validación de FastAPI, y lo que no existe da
**404**. ingesta usa `detalle` en español porque esa clave ya estaba publicada antes de pasar el código al inglés.

## Rutas por módulo

### `/ingesta`: los archivos y sus estadísticas

| Método y ruta | Qué devuelve |
|---|---|
| `GET /health` | si la memoria se puede abrir |
| `GET /data?type=&year=&month=&week=&code=&page=&per_page=` | los aptos para chunking, filtrados y paginados; `reorganizado` = fin de la última corrida de `organize` |
| `GET /data/file?origin=` o `?sha256=` | el registro de un archivo apto (uno de los dos parámetros); 404 si no existe o no es apto |
| `GET /data/content?origin=` | el archivo mismo, con su `Content-Type`; nunca sale de `data/ingesta/` |
| `GET /source` | la revisión del origen de una ingesta (030), que es **siempre `data/base/`**: si se encontró, qué tiene, cuántos nuevos y sus `problemas` (no existe, vacío, sin estructura, solapa ingesta...) |
| `POST /runs` `{simulate}` y `GET /runs[/{id}]` | correr la ingesta (como `organize`, pero **siempre copiando**: el origen queda intacto) en segundo plano; 422 con la revisión si el origen no sirve, 409 si ya hay una, 501 para `sql` |
| `GET /stats` y `/stats/summary`, `/types[/{tipo}]`, `/years[/{anio}]`, `/duplicates`, `/empty`, `/codes`, `/repeated[/{anio}]`, `/cleanup` | las estadísticas de la memoria, completas o por sección |

La memoria se abre y se cierra **en cada petición** (dependencia `Memory`). El convertidor de SQLAlchemy no se comparte
entre hilos, y así cada petición ve lo último que dejó `organize`. Las rutas de consulta nunca crean la memoria (si no existe, 503); solo `POST /runs` la crea, en el hilo de su corrida y con su propia conexión.

### `/data`: el grafo

| Método y ruta | Qué hace |
|---|---|
| `GET /health`, `GET /schema` | si Neo4j responde; etiquetas y relaciones permitidas |
| `GET/POST /nodes/{label}` | listar (paginado) / crear un nodo (sin `id`, se genera uno) |
| `GET/PUT/PATCH/DELETE /nodes/{label}/{id}` | leer / reemplazar propiedades / cambiar solo las enviadas (`null` borra) / borrar con sus relaciones |
| `GET /nodes/{label}/{id}/relationships` | las relaciones que entran o salen del nodo |
| `POST /relationships`, `GET /relationships/{type}` | crear una relación (validada contra el esquema) / listar un tipo |
| `GET/PUT/PATCH/DELETE /relationships/{type}/{source_label}/{source_id}/{target_label}/{target_id}` | una relación concreta |
| `POST /batch` | muchos nodos y relaciones en **una transacción**, con modos `replace`/`ensure`/`merge` y `replace_from` (ver [guia-data.md](guia-data.md#reglas-del-grafo)) |

### `/chunking`: conversión, chunking, experimentos y puntuaciones

| Método y ruta | Qué hace |
|---|---|
| `GET /health` | si Docling está instalado y si ingesta y data responden (por HTTP) |
| `POST /runs`, `GET /runs[/{id}]` | corrida de producción (feature 023): fragmenta los pendientes o una lista de `sha256s` con sus `parameters` y escribe `PIAA → JSON → SECCION → FRAGMENTOS`. Responde 202 y corre en segundo plano. |
| `GET /documents[/{sha256}[/chunks]]` | los documentos de producción y sus chunks |
| `POST /experiments` | experimento (feature 025): archivos + configuración de conversión + plan de estrategias por sección. Responde 202 en segundo plano; con `simulate`, 200. |
| `GET /experiments`, `GET/DELETE /experiments/{id}` | listar / ver (petición, progreso y resultados) / borrar |
| `GET /experiments/{id}/documents[/{sha256}[/chunks]]` | cómo se trató cada documento y cada sección, y sus chunks |
| `POST/GET /experiments/{id}/scores`, `GET/PUT/PATCH/DELETE .../scores/{score_id}` | puntuaciones del experimento |
| `GET /experiments/compare?ids=A&ids=B` | dos o más experimentos lado a lado: configuración, puntuaciones con promedios y números clave |

Todo lo pesado (convertir con Docling, fragmentar) corre **en un hilo propio**. La petición vuelve enseguida con un `id`
y el estado se consulta con `GET`. Hay un solo trabajo pesado a la vez.

## Cómo se hablan los módulos

Los módulos no se importan: chunking usa la misma API pública que cualquier cliente externo, contra
`ServerSettings.self_url` (por defecto `http://127.0.0.1:<puerto>`).

```
chunking                                         ingesta                     data
   │ GET /ingesta/data?page=N (una página a la vez) ──►│
   │ GET /ingesta/data/file?sha256=…                ──►│
   │ GET /ingesta/data/content?origin=…             ──►│
   │ (convierte y fragmenta)
   │ POST /data/batch  (un documento entero, una transacción) ────────────────────►│
   │ GET  /data/nodes/… (lo ya procesado, para no repetir)    ────────────────────►│
```

- **Una página a la vez:** chunking pide la página siguiente solo cuando terminó la anterior. Si `reorganizado` cambia
  entre páginas, porque ingesta se reorganizó en medio, corta la corrida.
- **Errores entre módulos:** dentro de chunking, la red caída, un timeout o un 5xx se vuelven `SourceError`/`SinkError`
  y cortan el trabajo. Un 404 de un archivo se vuelve `DocumentError` y falla solo ese documento.
- **Dónde está ese código:** `chunking/adapters/http/base_client.py` (el único que llama a `httpx`) y un cliente
  delgado por recurso en `adapters/ingesta/` y `adapters/data/`.

## Agregar una ruta

1. **Spec** de la feature con la ruta, su cuerpo, sus respuestas y sus errores.
2. **Esquemas** en `api/schemas.py` del módulo: dataclasses congeladas para el cuerpo y la respuesta. En ingesta las
   claves JSON van en español; en data y chunking, en inglés.
3. **Ruta** en `api/routes/<recurso>.py`: un `APIRouter` por archivo, sumado a `ROUTERS` en `api/routes/__init__.py`.
   La ruta solo traduce: recibe las dependencias (`Memory`, `Repository`, `Settings`…), llama al dominio o al
   repositorio, y convierte los errores en `HTTPException` con el formato del módulo.
4. **Orden:** una ruta fija (`/experiments/compare`) va **antes** que una con parámetro (`/experiments/{id}`), o FastAPI
   toma `compare` como id.
5. **Documentar las respuestas** de error en el decorador (`responses={404: …, 503: …}`) para que salgan en `/docs`.
6. **Si otro módulo la consume:** su cliente va en el `adapters/` de ese módulo, nunca importando al otro.
7. **Probarla:** sumar las peticiones al archivo de `http/` que corresponda y, si es un camino entre módulos, a
   `http/connections/`.

## Probar con los archivos `http/`

`http/` tiene peticiones listas para la extensión REST Client de VS Code ("Send Request" sobre cada una). Hay un archivo
por grupo de rutas:

| Carpeta o archivo | Qué prueba |
|---|---|
| `server.http` | `/health` y los `/docs` |
| `ingesta/` | `health`, `data` (lista, archivo, contenido), `stats` |
| `data/` | `nodes`, `relationships`, `batch` (cada uno crea sus datos de prueba y los borra; no correr `nodes` y `relationships` a la vez, comparten ids) |
| `chunking/` | `runs`, `documents`, `experiments`, `scores`, `health` |
| `connections/` | caminos entre módulos de punta a punta: `chunking-ingesta`, `chunking-data`, `ingesta-data`, `chunking-run`, `experiment-run`, `health` |

- **Peticiones encadenadas:** varias usan la respuesta de una anterior (`# @name`, `{{nombre.response.body.$.campo}}`).
  Se ejecutan de arriba a abajo. Es sintaxis de REST Client; httpyac no la entiende.
- **Datos reales:** las que escriben en el grafo usan ids de prueba (`test-*`) y limpian al final. Las de `chunking/`
  que no son `simulate` escriben sobre documentos reales, con sus ids definitivos.
- **Otro puerto:** cambiar la variable del principio de cada archivo (`@base`, `@graph`, `@chunking`, `@host`).

La documentación interactiva de cada módulo, con todos los esquemas, está en `http://127.0.0.1:8000/<módulo>/docs`.
