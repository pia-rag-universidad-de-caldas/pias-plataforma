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
Archivos y parseo (feature 042)
(:PIAA)-[:ES]->(:JSON)-[:VIENE_DE]->(:RAW)

Chunking oficial (features 043 y 045) y lo que cuelga del JSON
(:JSON)-[:TIENE_SECCION]->(:SECCION)-[:TIENE_FRAGMENTO]->(:FRAGMENTOS)
(:JSON)-[:TIENE]->(:HALLAZGOS)-[:DE_TIPO]->(:ANTIPATRON)-[:INCUMPLE]->(:NORMA);  (:HALLAZGOS)-[:EN]->(:FRAGMENTOS)
(:FACULTAD)-[:PERTENECE]->(:PROGRAMA)-[:HACE_PARTE]->(:ASIGNATURA)-[:PERTENECE]->(:PIAA)
(:CHAT)-[:GENERA]->(:CONSULTA)-[:SOBRE]->(:JSON);  (:CONSULTA)-[:RESPONDIDA_CON]->(:FRAGMENTOS)

Laboratorio (chunking 043, embeddings 046 y 055)
(:EXPERIMENTO)-[:EXP_USA]->(:JSON)
(:EXPERIMENTO)-[:EXP_GENERA]->(:EXP_SECCION)-[:EXP_TIENE_CHUNK]->(:EXP_CHUNK)
(:EXP_EMBEDDINGS)-[:EXP_USA]->(:EXPERIMENTO)
(:EXP_CHUNK)-[:EXP_TIENE_VECTOR]->(:EXP_EMBED)<-[:EXP_GENERA_VECTOR]-(:EXP_EMBEDDINGS)

Pipeline (features 028 y 044)
(:PIPE_CORRIDA)-[:PIPE_DE]->(:PIPELINE)
(:PIPE_CORRIDA)-[:PIPE_TIENE_ITERACION]->(:PIPE_ITERACION)-[:PIPE_USA]->(:EXPERIMENTO | :EXP_EMBEDDINGS)
(:PIPE_CORRIDA)-[:PIPE_TIENE_EVENTO]->(:PIPE_EVENTO)

Sin relaciones: CONFIG_OFICIAL (una por módulo), CORRIDA_PARSEO, CORRIDA_CHUNKING, CORRIDA_EMBEDDINGS
De antes de la 043, en el esquema pero sin uso: EXP_DOCUMENTO, EXP_PUNTUACION, EXP_TIENE_SECCION,
EXP_TIENE_PUNTUACION y (:JSON)-[:VIENE_DE]->(:EXP_DOCUMENTO)
```

Los vectores oficiales no son nodos: son una propiedad **por modelo**, `embedding_<modelo>_<dim>`, de `FRAGMENTOS`
(feature 055). Los de laboratorio van en un `EXP_EMBED` por experimento de embeddings y chunk, con la misma propiedad.
Cada propiedad tiene su índice vectorial (`vec_fragmentos_*`, `vec_exp_embed_*`; `/data/vectors/indexes`, reglas en
`schema/vector_rules.py`: `VECTOR_LABELS` = `FRAGMENTOS` y `EXP_EMBED`), porque Neo4j admite uno por etiqueta y
propiedad. `data` no conoce los modelos: los nombres los arma `embeddings`, y `data` solo valida su patrón.
`?omit=embedding` deja fuera todas las propiedades de vector. Los guardados antes de la 055 (en `embedding`) se mueven
una vez con `prueba-chunking migrate-vectors [--simulate]` (`repository/maintenance.py`, `VectorMigration`), con el
servidor parado.

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
4. **Si otro módulo escribe esa etiqueta:** ver [Hacer que otro módulo escriba lo nuevo](#hacer-que-otro-módulo-escriba-lo-nuevo).
5. **Si la etiqueta se borra cuando se reprocesa su padre**, ver [Reglas del grafo](#reglas-del-grafo) (`COMPOSITION`).

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

Las reglas que no son "qué existe" viven en `schema/` y en `repository/`:

| Regla | Dónde | Qué decide |
|---|---|---|
| **Composición** | `COMPOSITION` (`schema/piaa_schema.py`) | qué relaciones se siguen al borrar los descendientes de un nodo con `replace_from` en `POST /data/batch`, es decir, qué se considera "parte de" un nodo |
| **Modos de escritura** | `NodeMode` (`models/piaa.py`) y `GraphBatchWriter._merge_nodes` (`repository/batch_writer.py`) | `replace`: las propiedades pasan a ser las enviadas. `ensure`: se crea si no existe, sin tocar lo que haya. `merge`: pone las enviadas y conserva las demás. |
| **Validación de un lote** | `batch_problems` (`schema/batch_rules.py`) y `GraphBatchWriter.write` (extremos inexistentes) | antes de escribir: relaciones fuera del esquema, nodos o relaciones repetidos, ids vacíos y extremos inexistentes. Cualquiera da 422 y no se escribe nada. |
| **Propiedades permitidas** | `PropertyValue` (`models/piaa.py`) | valores simples o listas homogéneas. Un mapa da 422 (se guarda como texto JSON). |

### Cambiar la composición (qué se borra al reprocesar)

`COMPOSITION` (`schema/piaa_schema.py`, junto a la definición de cada relación) lista los tipos que significan "es
parte de": `ES`, `TIENE_SECCION`, `TIENE_FRAGMENTO`, `TIENE`, `GENERA`, `EXP_GENERA`, `EXP_TIENE_CHUNK`,
`EXP_TIENE_PUNTUACION`, `PIPE_TIENE_ITERACION`, `PIPE_TIENE_EVENTO` y, desde la 055, `EXP_TIENE_VECTOR` y
`EXP_GENERA_VECTOR` (borrar un experimento de embeddings es `replace_from` su `EXP_EMBEDDINGS`: se lleva solo sus
`EXP_EMBED`). Sus tests: `tests/data/schema/test_batch_rules.py`,
`tests/data/repository/test_batch_writer.py` y `tests/data/api/routes/test_batch.py` (que `replace_from` nunca siga una
relación compartida). Antes de sumar o quitar uno, comprobar dos cosas:

- **No borra nodos compartidos.** Por eso `DE_TIPO` o `INCUMPLE` no están (borrarían el catálogo de `ANTIPATRON` y
  `NORMA`), ni `EXP_USA` (borrar un experimento nunca borra el `JSON` oficial que usó, ni uno de embeddings el
  experimento de chunking), ni `PIPE_USA`, ni `VIENE_DE` (parsear de nuevo nunca borra el `RAW`).
- **No borra lo que debe sobrevivir a un reproceso.** Hoy `TIENE` está en la lista, así que rechunkear o
  parsear de nuevo un `JSON` borra sus `HALLAZGOS`. Es una decisión pendiente.

Una relación nueva que **no** sea de composición no se agrega a la lista. Si es de composición, se agrega aquí y se
prueba con un `replace_from` (`http/data/batch.http` tiene el patrón).

### Agregar una regla de validación

Una regla sobre lo que se envía va en `schema/batch_rules.py` (`batch_problems`) o, para vectores, en
`schema/vector_rules.py`; una que necesita leer el grafo, en el repositorio (`GraphBatchWriter.write` o el método de
CRUD correspondiente). Se informa con `BatchError` o con una `HTTPException` desde la ruta. La validación debe correr **antes** de escribir o dentro de la transacción, para
que un lote inválido no deje nada a medias. La ruta (`api/routes/`) solo traduce: no decide reglas.

### Escribir Cypher nuevo

En `PiaaRepository`, por medio de `GraphAdapter.read`/`write` o de `transaction()` cuando son varias sentencias:

- Etiquetas y tipos **solo** con `_name(enum)`. Nunca concatenar texto que venga de una petición.
- La única excepción es una propiedad de vector (055): pasa por `repository/cypher.vector_property`, que exige el
  patrón `embedding_[a-z0-9_]{1,120}` de `schema/vector_rules.py` (si no, `GraphError`).
- Todo valor va en parámetros (`$id`, `$properties`).
- El tipo de la consulta es `LiteralString`, y mypy avisa si se cuela un `str` armado con datos.

## Hacer que otro módulo escriba lo nuevo

Ningún módulo importa `data`: escriben por HTTP con `POST /data/batch` y cada uno tiene su propia lista cerrada de lo
que puede escribir. Los módulos de trabajo (`ingesta`, `parsing`, `chunking`, `embeddings`) solo hablan con `data`.

1. **Sus nombres:** `parsing`, `chunking` y `embeddings` tienen `GraphLabel` y `GraphRelation` en `models/batch.py`:
   sumar ahí la etiqueta y la relación, con los mismos valores que en `data`. `embeddings` tiene un test que las
   compara con el esquema (`tests/embeddings/models/test_data_names.py`); ingesta escribe solo `RAW`
   (`adapters/raw_store.py`).
2. **La forma guardada:** `models/stored.py` del módulo, un `TypedDict` con las propiedades del nodo o de la relación
   nueva (o la clave nueva en el que ya existe). La comparten quien escribe y quien lee.
3. **Quien arma el lote**, en el dominio: `parsing/domain/graph.py` (`ParsedGraph`), `chunking/domain/production/graph.py`
   (`OfficialGraph`, `RunGraph`), `chunking/domain/experiments/graph.py` (`ExperimentGraph`), `embeddings/domain/batches.py`.
   Crea los `GraphNode` y `GraphLink` nuevos con ese `TypedDict` y el modo que corresponda (`merge` para escribir solo
   las propiedades propias sobre un nodo de otro módulo, como chunking sobre el `JSON` de parsing).
4. **Si también lo lee:** el mapper en `adapters/data/` (`mappers.py`) lo lee con `stored(raw, TuTipo)` e indexando
   (`p["clave"]`, no `p.get`: así mypy revisa la clave) y convierte las propiedades del grafo, en español, al modelo en
   inglés. Es el único lugar donde se hace esa traducción. Para no traer propiedades pesadas, `?omit=` en la lectura.
5. Un test en `tests/<módulo>/` con `httpx.MockTransport` para el mapper o el cliente.

## Verificar

```bash
uv run ruff format && uv run ruff check && uv run mypy && uv run pytest
```

Contra el Neo4j de prueba:

- `GET /data/schema` muestra lo nuevo.
- `http/data/nodes.http`, `relationships.http` y `batch.http`, que arman el grafo de prueba, prueban los errores y
  limpian. Se pueden correr de nuevo después del cambio para comprobar que no se rompió nada.
- Una petición que use la relación al revés debe dar 422.
- Si se tocó `COMPOSITION`: un `replace_from` que borre lo esperado y nada más. Revisar los nodos compartidos.
- Si otro módulo lo escribe: `http/connections/ingesta-data.http`, `chunking-data.http` o `embeddings-data.http`.
- Al terminar, apagar el contenedor: `docker stop neo4j-prueba`.

Documentar en `CLAUDE.md` (sección del paquete `data` y la del módulo que lo escribe) y tachar las tareas del spec.
