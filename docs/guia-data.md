# Guía de cambios en data (grafo)

Paso a paso para cambiar el grafo de `src/data/`: agregar una etiqueta de nodo, una relación, cambiar una regla del
grafo y hacer que otro módulo escriba lo nuevo. Antes, leer [arquitectura.md](arquitectura.md#data-por-dentro).

## Cómo está definido el grafo

Dos archivos dicen **qué existe**; el resto del módulo se adapta solo:

| Archivo | Qué define |
|---|---|
| `models/piaa.py` | `Label` (etiquetas de nodo) y `RelationshipType` (tipos de relación), como `StrEnum`. El valor es el nombre tal cual en Neo4j. |
| `schema/piaa_schema.py` | `RELATIONSHIPS`: cada relación permitida como `RelationshipDefinition(tipo, origen, destino)`. Un mismo tipo puede tener varios pares (por ejemplo, `PERTENECE`). |

Lo que se adapta solo a partir de esos dos archivos:

- **Rutas:** `/data/nodes/{label}` acepta cualquier valor de `Label`, porque FastAPI valida el parámetro contra el
  enum. `/data/relationships/...` y `POST /data/batch` validan contra `RELATIONSHIPS`, y lo que no está da 422.
- **Restricciones:** al arrancar, `PiaaRepository.ensure_constraints` crea una restricción de unicidad de `id` por cada
  etiqueta (`piaa_id_<LABEL>`).
- **Esquema publicado:** `GET /data/schema` devuelve las etiquetas y relaciones permitidas.

El grafo actual:

```
Producción
(:CHAT)-[:GENERA]->(:CONSULTA)-[:SOBRE]->(:JSON)-[:TIENE_SECCION]->(:SECCION)-[:TIENE_FRAGMENTO]->(:FRAGMENTOS)
(:CONSULTA)-[:RESPONDIDA_CON]->(:FRAGMENTOS)<-[:EN]-(:HALLAZGOS)-[:DE_TIPO]->(:ANTIPATRON)-[:INCUMPLE]->(:NORMA)
(:FACULTAD)-[:PERTENECE]->(:PROGRAMA)-[:HACE_PARTE]->(:ASIGNATURA)-[:PERTENECE]->(:PIAA)-[:ES]->(:JSON)
(:JSON)-[:TIENE]->(:HALLAZGOS)

Experimentos (feature 025)
(:EXPERIMENTO)-[:EXP_USA]->(:EXP_DOCUMENTO)-[:EXP_TIENE_SECCION]->(:EXP_SECCION)-[:EXP_TIENE_CHUNK]->(:EXP_CHUNK)
(:EXPERIMENTO)-[:EXP_GENERA]->(:EXP_SECCION)
(:EXPERIMENTO)-[:EXP_TIENE_PUNTUACION]->(:EXP_PUNTUACION)
```

Los valores de los enums (`PIAA`, `TIENE_SECCION`…) son **datos guardados en Neo4j**: siguen en español y no se
renombran sin migrar el grafo. El código alrededor va en inglés.

## Antes de cualquier cambio

1. **Spec primero**: `spec/features/NNN-nombre/` con `spec.md`, `plan.md` y `tasks.md`, más su línea en el roadmap.
   Incluir un dibujo del grafo con lo nuevo.
2. **Neo4j de prueba** en Docker, nunca el real:

   ```bash
   docker run -d --rm --name neo4j-prueba -p 17687:7687 -e NEO4J_AUTH=neo4j/clave-prueba neo4j:2026.07.1
   NEO4J_PASSWORD=clave-prueba uv run prueba-chunking serve --neo4j-url neo4j://localhost:17687 --port 18000 \
       --memory /tmp/copia.sqlite3
   ```

## Flujo: agregar una etiqueta de nodo

Ejemplo: `EVALUACION`.

```
models/piaa.py (Label) ─► schema/piaa_schema.py (sus relaciones) ─► ¿composición? ─► otros módulos ─► http/ + docs
```

1. **Enum** (`models/piaa.py`): agregar `EVALUACION = "EVALUACION"` a `Label`. Con eso ya existen
   `GET/POST /data/nodes/EVALUACION`, `GET/PUT/PATCH/DELETE /data/nodes/EVALUACION/{id}` y la restricción
   `piaa_id_EVALUACION`, que se crea al arrancar el servidor.
2. **Relaciones:** una etiqueta sin relaciones queda suelta. Seguir el flujo siguiente para conectarla.
3. **Docstring del esquema** (`schema/piaa_schema.py`): actualizar el dibujo del grafo.
4. **Si otro módulo escribe esa etiqueta:** ver [Hacer que chunking escriba lo nuevo](#hacer-que-chunking-escriba-lo-nuevo).
5. **Si la etiqueta se borra cuando se reprocesa su padre**, ver [Reglas del grafo](#reglas-del-grafo) (`_COMPOSITION`).

## Flujo: agregar una relación

Ejemplo: `(:EVALUACION)-[:EVALUA]->(:FRAGMENTOS)`.

1. **Enum** (`models/piaa.py`): `EVALUA = "EVALUA"` en `RelationshipType`, si el tipo es nuevo. Un tipo con espacios
   no se puede (habría que ponerle comillas invertidas en todo el Cypher): `HACE PARTE` del diseño se escribe
   `HACE_PARTE`.
2. **Esquema** (`schema/piaa_schema.py`): agregar a `RELATIONSHIPS`
   `RelationshipDefinition(_T.EVALUA, _L.EVALUACION, _L.FRAGMENTOS)`. **El sentido importa**: la relación al revés es
   422. Si el mismo tipo conecta otro par, va otra línea con el mismo tipo.
3. Con eso ya funcionan `POST /data/relationships`, `/data/relationships/EVALUA/...` y su uso dentro de
   `POST /data/batch`. En un mismo par de nodos hay a lo sumo una relación de cada tipo.
4. Actualizar el dibujo del docstring del esquema.

## Reglas del grafo

Las reglas que no son "qué existe" viven en `repository/piaa_repository.py`:

| Regla | Dónde | Qué decide |
|---|---|---|
| **Composición** | `_COMPOSITION` | qué relaciones se siguen al borrar los descendientes de un nodo con `replace_from` en `POST /data/batch`, es decir, qué se considera "parte de" un nodo |
| **Modos de escritura** | `NodeMode` (`models/piaa.py`) y `_merge_nodes` | `replace`: las propiedades pasan a ser las enviadas. `ensure`: se crea si no existe, sin tocar lo que haya. `merge`: pone las enviadas y conserva las demás. |
| **Validación de un lote** | `write_batch` | antes de escribir: relaciones fuera del esquema, nodos o relaciones repetidos, ids vacíos y extremos inexistentes. Cualquiera da 422 y no se escribe nada. |
| **Propiedades permitidas** | `PropertyValue` (`models/piaa.py`) | valores simples o listas homogéneas. Un mapa da 422 (se guarda como texto JSON). |

### Cambiar la composición (qué se borra al reprocesar)

`_COMPOSITION` lista los tipos que significan "es parte de": `ES`, `TIENE_SECCION`, `TIENE_FRAGMENTO`, `TIENE`,
`GENERA`, `EXP_GENERA`, `EXP_TIENE_CHUNK` y `EXP_TIENE_PUNTUACION`. Antes de sumar o quitar uno, comprobar dos cosas:

- **No borra nodos compartidos.** Por eso `DE_TIPO` o `INCUMPLE` no están (borrarían el catálogo de `ANTIPATRON` y
  `NORMA`), ni `EXP_USA` (un `EXP_DOCUMENTO` lo usan varios experimentos).
- **No borra lo que debe sobrevivir a un reproceso.** Hoy `TIENE` está en la lista, así que reprocesar un `JSON` borra
  sus `HALLAZGOS`. Es una decisión pendiente.

Una relación nueva que **no** sea de composición no se agrega a la lista. Si es de composición, se agrega aquí y se
prueba con un `replace_from` (`http/data/batch.http` tiene el patrón).

### Agregar una regla de validación

Va en el repositorio, dentro de `write_batch` (o del método de CRUD correspondiente), y se informa con `BatchError` o
con una `HTTPException` desde la ruta. La validación debe correr **antes** de escribir o dentro de la transacción, para
que un lote inválido no deje nada a medias. La ruta (`api/routes/`) solo traduce: no decide reglas.

### Escribir Cypher nuevo

En `PiaaRepository`, por medio de `GraphAdapter.read`/`write` o de `transaction()` cuando son varias sentencias:

- Etiquetas y tipos **solo** con `_name(enum)`. Nunca concatenar texto que venga de una petición.
- Todo valor va en parámetros (`$id`, `$properties`).
- El tipo de la consulta es `LiteralString`, y mypy avisa si se cuela un `str` armado con datos.

## Hacer que chunking escriba lo nuevo

`chunking` no importa `data`: escribe por HTTP con `POST /data/batch` y tiene su propia lista cerrada de lo que puede
escribir.

1. `chunking/models/batch.py`: sumar la etiqueta a `GraphLabel` y la relación a `GraphRelation`. Mismos valores que en
   `data`.
2. `chunking/models/stored.py`: un `TypedDict` con las propiedades del nodo o de la relación nueva (o la clave nueva en
   el que ya existe). Es la forma guardada que comparten quien escribe y quien lee.
3. El dominio de chunking que arma el lote (`domain/hierarchy.py` para producción, `domain/experiment_graph.py` para
   experimentos) crea los `GraphNode` y `GraphLink` nuevos con ese `TypedDict` como propiedades y el modo que
   corresponda.
4. Si chunking también lo **lee**, el mapper en `adapters/data/` (`mappers.py` o `experiment_mappers.py`) lo lee con
   `stored(raw, TuTipo)` e indexando (`p["clave"]`, no `p.get`: así mypy revisa la clave) y convierte las propiedades
   del grafo, en español, al modelo en inglés. Es el único lugar donde se hace esa traducción.
5. Un test en `tests/chunking/` con `httpx.MockTransport` para el mapper o el cliente.

## Verificar

```bash
uv run ruff format && uv run ruff check && uv run mypy && uv run pytest
```

Contra el Neo4j de prueba:

- `GET /data/schema` muestra lo nuevo.
- `http/data/nodes.http`, `relationships.http` y `batch.http`, que arman el grafo de prueba, prueban los errores y
  limpian. Se pueden correr de nuevo después del cambio para comprobar que no se rompió nada.
- Una petición que use la relación al revés debe dar 422.
- Si se tocó `_COMPOSITION`: un `replace_from` que borre lo esperado y nada más. Revisar los nodos compartidos.
- Si chunking lo escribe: `http/connections/chunking-data.http` o `experiment-run.http`.
- Al terminar, apagar el contenedor: `docker stop neo4j-prueba`.

Documentar en `CLAUDE.md` (sección del paquete `data` y la de chunking si aplica) y tachar las tareas del spec.
