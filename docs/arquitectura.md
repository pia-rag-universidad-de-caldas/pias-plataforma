# Arquitectura actual

Cómo está armado el proyecto hoy: qué módulos hay, cómo se reparten el trabajo y qué reglas los mantienen separados.
Para cambiar algo concreto, ver las guías de [README.md](README.md) y, para las rutas, [api.md](api.md).

## El flujo de punta a punta

```
POST /ingesta/uploads (049: el front sube documentos; no ingesta)
   ▼
data/base/<anio>/<mes>/<semana>/<codigo>/<archivo>
   │ ingesta (POST /ingesta/runs): copia lo nuevo, clasifica todo el corpus
   ▼
data/ingesta/<categoria>/<tipo>/…  +  memoria SQLite (data/ingesta/.memoria.sqlite3)
   │ ingesta, al final de cada corrida: sube los vigentes (POST /data/batch)
   ▼
data: (:RAW {id: sha256, contenido: base64, vigente})
   │ parsing (POST /parsing/runs): lee el RAW, Docling con configuración fija (+ OCR donde falta texto)
   ▼
data: (:PIAA {id: codigo})-[:ES]->(:JSON {id: sha256, documento: DoclingDocument})-[:VIENE_DE]->(:RAW)
   │ chunking (POST /chunking/runs o /chunking/experiments): chunkers de docling-core
   ▼
data: (:JSON)-[:TIENE_SECCION]->(:SECCION)-[:TIENE_FRAGMENTO]->(:FRAGMENTOS)        (oficial)
      (:EXPERIMENTO)-[:EXP_GENERA]->(:EXP_SECCION)-[:EXP_TIENE_CHUNK]->(:EXP_CHUNK)   (laboratorio)
   │ embeddings (POST /embeddings/runs o /embeddings/experiments): modelo de vectores local
   ▼
data: FRAGMENTOS.embedding_<modelo>_<dim>  ·  (:EXP_CHUNK)-[:EXP_TIENE_VECTOR]->(:EXP_EMBED)<-[:EXP_GENERA_VECTOR]-(:EXP_EMBEDDINGS)
      + un índice vectorial por modelo y etiqueta (vec_fragmentos_*, vec_exp_embed_*; POST /data/vectors/search)

pipeline: el único que orquesta. Le dice a cada módulo qué ids procesar y espera a que termine.

Una pregunta (consultas, POST /consultas/ask o `prueba-chunking ask`):
pregunta ──► (adjuntos, 048 fase 2: un documento → POST /parsing/preview → trozos; una imagen → llm, modelo de visión → descripción)
         ──► embeddings (POST /embeddings/vectors: texto → vector + nombre del índice de su modelo)
         ──► data (POST /data/vectors/search: los FRAGMENTOS, o los EXP_CHUNK de un experimento, más parecidos)
         ──► llm (POST /llm/chat: la respuesta, con esos fragmentos numerados como contexto; Ollama)
         ──► data (POST /data/batch: (:CHAT)-[:GENERA]->(:CONSULTA)-[:RESPONDIDA_CON]->(:FRAGMENTOS | :EXP_CHUNK))
```

1. **ingesta** recorre `data/base/`, copia cada archivo nuevo a `data/ingesta/` (nunca mueve ni modifica el origen),
   clasifica el corpus entero (vacío, extraño, duplicado por hash, duplicado por código, incompleto, vigente, apto
   para chunking) y lleva una memoria SQLite con la metadata de cada archivo. Al terminar, **sube a `data` todos los
   aptos** que todavía no estén, un nodo `RAW` por contenido (`sha256`), y marca `vigente: false` los que dejaron de
   serlo (feature 042). Documentos nuevos llegan a `data/base/` por `POST /ingesta/uploads` (049), que solo los
   guarda: la ingesta siguiente los procesa.
2. **parsing** recibe una lista de `sha256` (o, sin ella, toma todos los `RAW` vigentes que faltan), lee cada `RAW` de
   `data`, lo convierte con Docling **con una configuración fija** (la más completa; OCR solo en las páginas sin
   texto) y guarda el `DoclingDocument` entero, comprimido, en un `JSON`. Un documento que se corta por tiempo queda
   `parcial` y se retoma desde sus páginas pendientes (feature 042). `POST /parsing/preview` (048 fase 2) lee un
   documento con la misma configuración sin guardar nada.
3. **chunking** lee los `DoclingDocument` de `data` y los parte con los chunkers de docling-core (`hybrid`,
   `hierarchical`, `page`). Tiene dos usos (features 043 y 045):
   - **corridas** (`/chunking/runs`): lo oficial, con la **configuración activa**; reemplazan lo que colgaba de cada
     `JSON`. Un documento nunca se chunkea dos veces con la misma configuración sobre el mismo parseo;
   - **experimentos** (`/chunking/experiments`): una configuración aparte, con etiquetas `EXP_*`, para compararla. Un
     experimento terminado se **aplica** (`/apply`): su configuración pasa a ser la activa. No se promueve.
4. **embeddings** calcula los vectores de los chunks oficiales (corridas) o de un experimento de chunking
   (experimentos), los escribe en `data` y le pide a `data` el índice vectorial de su modelo (feature 046). Desde la
   055 cada modelo tiene su propiedad y su índice: varios modelos conviven y se cambia de uno a otro sin cortar el chat.
5. **data** es la única puerta a Neo4j: valida todo contra el esquema del grafo, lo escribe en lotes transaccionales,
   dice qué falta por parsear o chunkear (`/data/progress/*`) y busca por similitud (`/data/vectors/search`).
6. **llm** es el único que habla con Ollama: los modelos admitidos (`config.MODELS`), sus descargas, la configuración
   activa y `POST /llm/chat` (con imágenes para un modelo de visión). No sabe de documentos (feature 047).
7. **pipeline** junta todo en dos plantillas: `produccion` (ingesta → parseo → chunking → embeddings, con las
   configuraciones activas) y `laboratorio` (un lote elegido; el actor `lab` prueba tríos chunking + embeddings + llm
   hasta aprobar uno, que se aplica) (features 044 y 050).
8. **consultas** responde preguntas con los documentos oficiales (el RAG): vectoriza la pregunta, busca los fragmentos
   parecidos, le pide la respuesta a `llm` citándolos y guarda el chat en `data` (feature 048). Siempre cita:
   si ningún fragmento pasa `min_score`, dice que no encontró nada y no llama al LLM. Con adjuntos (fase 2), también
   busca lo parecido a documentos e imágenes, que nunca se guardan.

## Los módulos

Todo vive en `src/`, en un solo proyecto de uv (`pyproject.toml`, `module-name = ["ingesta", "data", "chunking",
"pipeline", "server", "common", "parsing", "embeddings", "llm", "consultas"]`). `src/labs/` es un borrador de otra
persona: no es parte del servidor. `docker/` tiene el proyecto de Docker Compose de Neo4j y Ollama (feature 054).

| Paquete | Prefijo | Qué hace | Guarda en | Extra de uv |
|---|---|---|---|---|
| `ingesta` | `/ingesta` | organiza `data/base/` → `data/ingesta/`, estadísticas, publica los aptos como `RAW` | SQLite (vía SQLAlchemy) y disco; `RAW` en data | — |
| `data` | `/data` | CRUD del grafo, lotes, avance, índices y búsqueda vectorial | Neo4j | `data` (driver `neo4j`) |
| `parsing` | `/parsing` | `RAW` → `DoclingDocument` en un `JSON` (configuración fija, OCR) | nada propio: todo en data | `parse` (Docling completo + `onnxruntime` para RapidOCR) |
| `chunking` | `/chunking` | `JSON` → `SECCION`/`FRAGMENTOS` (oficial) o `EXP_*` (experimentos); configuración activa | nada propio: todo en data | `chunk` (`docling-core[chunking]`, sin PyTorch) |
| `embeddings` | `/embeddings` | vectores por modelo de `FRAGMENTOS` o, en experimentos, `EXP_EMBED`; configuración activa; texto → vector (`/vectors`) | nada propio: todo en data | `embed` (`torch` + `transformers`) |
| `llm` | `/llm` | Ollama: modelos admitidos y sus descargas, configuración activa, chat (con imágenes) | la configuración en data; los modelos, en Ollama | — (`httpx` hacia Ollama) |
| `pipeline` | `/pipeline` | plantillas de etapas, corridas, actores externos | nada propio: todo en data | — |
| `consultas` | `/consultas` | el RAG: búsqueda, preguntas con fuentes, chats, su configuración | `CHAT`/`CONSULTA` y su configuración en data | — |
| `server` | `/` | raíz de composición: monta los ocho módulos, `/health`, `/processes`, la CLI (`console`, `serve`, `ask`) y la consola | — | — |
| `common` | — | infraestructura sin dominio: cliente HTTP base, errores de API, guardas, procesos, logs, reloj | — | — |

Sin un extra, su módulo arranca igual y responde 503 en lo que lo necesita (`GET /<módulo>/health` lo dice). Un
`uv sync` deja instalados **solo** los extras que se nombran: `uv sync --extra data --extra parse --extra chunk
--extra embed` para tenerlo todo.

### Regla principal: los módulos no se importan entre sí

- Ningún módulo importa a otro. Solo `server` los importa a todos, para montarlos. Todos pueden importar `common`, que
  no importa a ninguno (`tests/common/test_independent.py`).
- Cada módulo tiene un `ruff.toml` que extiende el `pyproject.toml` y prohíbe importar a los demás (`TID251`,
  `extend-banned-api`).
- **Los módulos de trabajo** (`ingesta`, `parsing`, `chunking`, `embeddings`, `llm`) **solo hablan con `data`**, por
  HTTP al mismo servidor (`ServerSettings.self_url`); `llm` además con Ollama, que no es un módulo sino un servicio
  externo (como Neo4j para `data`). No saben que los otros existen y no eligen qué procesar: reciben listas
  explícitas de ids (o, a mano, «todo lo que falta»). Ruff no ve una ruta escrita como texto, así que lo vigila
  `tests/common/test_module_rule.py`: ninguno nombra el prefijo de otro módulo que no sea `/data`.
- **Los consumidores** (`pipeline` y `consultas`; el laboratorio, cuando exista) pueden llamar a los otros módulos por
  su API pública. Solo el pipeline orquesta trabajos (les pasa los ids y espera); `consultas` llama a `embeddings`,
  `data` y `llm` para responder una pregunta. A ellos no los revisa `test_module_rule.py`, pero su `ruff.toml` les
  prohíbe importar a los demás igual que a todos.
- Cada módulo se puede usar solo, sin el pipeline: sus rutas reciben los ids a mano (consola, `http/`, `curl`).

Así cada módulo se puede separar mañana en su propio servicio sin tocar su dominio: solo cambia la URL.

## Capas dentro de cada módulo

Todos siguen el mismo esquema tipo *clean architecture*. Las dependencias van siempre hacia adentro:

```
api/ (HTTP)  ──►  domain/ (reglas)  ──►  models/ (datos e interfaces)  ◄──  adapters/ , repository/
                                                                              (implementan las interfaces)
```

| Capa | Qué contiene | Qué NO puede hacer |
|---|---|---|
| `config/` | parámetros y valores por defecto (en parsing y chunking, `config/docling.py`: lo fijo y su versión) | — |
| `models/` | dataclasses congeladas e interfaces (`Protocol`/ABC), un archivo por función (`concepts`, `requests`, `results`, `ports`, `batch`, `stored`...) | importar infraestructura o tener lógica |
| `domain/` | reglas de negocio, clases con métodos estáticos | importar el ORM, el driver, FastAPI, `httpx`, `pathlib`, Docling, ni hacer I/O o registrar logs |
| `repository/` | (ingesta y data) repositorios sobre un adaptador | escribir SQL fuera del adaptador; en data, Cypher solo aquí |
| `tables/` | (ingesta) qué tablas hay, sin sintaxis | — |
| `adapters/` | el borde con el mundo: base de datos, disco, Neo4j, Docling, modelos, HTTP | — (es el único lugar que puede importar esas librerías) |
| `api/` | FastAPI: rutas, dependencias, esquemas, registros y colas de trabajo | contener reglas de negocio |

Qué librería puede importar quién (Ruff `TID251` en `pyproject.toml`; las carpetas `adapters/` y `api/` de cada
módulo lo tienen ignorado y la convención dice cuál archivo):

| Librería | Solo en |
|---|---|
| `sqlalchemy`, `sqlite3` | `ingesta/adapters/sqlalchemy_converter.py` |
| `pathlib`, `shutil`, `os`, `stat` | `ingesta/adapters/local_files.py` (y los adaptadores que lo necesitan para cachés de modelos) |
| `neo4j` | `data/adapters/neo4j_adapter.py` |
| `docling` | `parsing/adapters/` (diferido) |
| `docling_core` | `chunking/adapters/docling_chunkers.py` (diferido) |
| `torch`, `transformers` | `embeddings/adapters/` (diferido; por convención: no están en `banned-api`) |
| `httpx` | los `adapters/` de cada módulo (en `llm`, `adapters/ollama_client.py` es el único que habla con Ollama), `common/http/` y `server/ask.py` |
| `fastapi`, `starlette`, `uvicorn` | `*/api/`, `common/api/` y `server/` |
| `asciimatics` | `server/console/toolkit.py` (por convención, con `import_module`) |

Las librerías pesadas se importan **dentro** de los métodos (`import_module`), para que el servidor arranque y mypy
pase sin el extra.

## ingesta por dentro

```
api/routes/ ──► domain/ (Ingestion, Discovery, Organization, Classifier, Duplicates, RawSync, Statistics…)
                    │ usa los Protocol de models/repositories.py y models/raw.py (RawStore)
                    ▼
repository/ (DbFileRepository, DbCategoryRepository, DbRunRepository, DbIngestionRepository, DbUploadRepository)
                    │ sobre models.ORMAdapter
                    ▼
adapters/sql_adapter.py (SQLORMAdapter: reglas del CRUD, migraciones)
                    │ sobre models.SQLConverter
                    ▼
adapters/sqlalchemy_converter.py (SqlAlchemyConverter: el único que habla SQL)

adapters/local_files.py (LocalFileAdapter: el único que toca el disco)
adapters/raw_store.py   (HttpRawStore: los RAW de data, por HTTP)
```

- **Las tablas se describen, no se escriben en SQL.** `tables/` define cada tabla con `TableSpec`/`ColumnSpec`. Cada
  columna se llama igual que el campo de su entidad en `models/entities.py` (en español). El adaptador las crea
  (`from_scratch`) o las abre y migra (`from_existing`); una tabla nueva con `created_if_missing` se crea al abrir una
  memoria vieja (la de `corridas_api`, feature 041, y la de `subidas`, 049).
- **Migraciones por regla.** Cada `TableSpec` puede tener `needs_migration(columnas) -> bool`. Si dice que sí, el
  adaptador reconstruye la tabla en una transacción: copia, borra, crea y reinserta.
- **El disco también es un adaptador.** `FileReader`/`FileWriter` (`models/files.py`) trabajan con rutas relativas a
  una raíz, como texto. El origen de una ingesta solo se lee. Copias atómicas (`*.parcial` y renombrar) con el sha256
  calculado en la copia.
- **Clasificación con todo el corpus.** `Classifier.classify` evalúa cada categoría por separado, elige la principal
  por prioridad y esa decide la carpeta. Un archivo nuevo puede desplazar a un vigente; `Organization.relocate` lo
  mueve en la misma corrida.
- **Publicación en data** (`domain/raw_sync.py`, feature 042): después de clasificar, `RawSync.plan` compara los aptos
  con los `RAW` que `data` tiene y `RawSync.run` sube los que faltan, uno por lote (un archivo que no cabe en
  `max_body_bytes` con su base64 falla solo) y retira los que dejaron de ser aptos. Sin `data`, la ingesta termina
  igual y lo dice en `resultado.en_data.aviso`; la corrida siguiente lo reintenta.
- **Subidas** (`domain/uploads.py`, feature 049): `POST /ingesta/uploads` (multipart `files`/`files[]` + `code`,
  leído con la biblioteca estándar en `api/multipart.py`) guarda cada pdf/doc/docx en
  `<anio>/<MM_Mes>/Semana_NN/<codigo>/` de la fecha de subida, con el prefijo de fecha de los nombres del corpus, con
  `FileWriter.write_new` (nunca pisa) y una fila en la tabla `subidas`; responde `guardado`, `ya_existe` (mismo
  sha256) o `rechazado` con su motivo. Una subida a la vez (un lock). No ingesta: eso lo hace después el pipeline.
- **El dominio no imprime ni registra.** Informa con `IngestionObserver`; la API lo registra.

## data por dentro

```
api/routes/ ──► repository/piaa_repository.py      (PiaaRepository: CRUD y Cypher)
            ──► repository/batch_writer.py         (GraphBatchWriter: POST /batch, una transacción)
            ──► repository/progress_repository.py  (qué falta por parsear o chunkear)
            ──► repository/vector_repository.py    (índices y búsqueda vectorial)
                    │ validan con schema/ (piaa_schema.py, batch_rules.py, vector_rules.py)
                    ▼
                models.GraphAdapter ◄── adapters/neo4j_adapter.py (Neo4jGraphAdapter: el único que importa neo4j)
```

- **Qué existe en el grafo** lo dicen los enums `Label` y `RelationshipType` (`models/piaa.py`) y la tupla
  `RELATIONSHIPS` (`schema/piaa_schema.py`), con cada relación permitida y sus extremos. `COMPOSITION`, junto a ella,
  dice qué relaciones son «parte de» (las que sigue `replace_from`).
- **Cypher seguro.** Etiquetas y tipos se concatenan, pero **solo** valores de los enums; todo lo demás va en
  parámetros.
- **Nodos.** Etiqueta, `id` de texto único por etiqueta (restricción `piaa_id_<LABEL>`, creada al arrancar) y
  propiedades simples o listas homogéneas. `?omit=` deja fuera propiedades pesadas al leer (`contenido` de un `RAW`,
  `documento` de un `JSON`; `embedding` deja fuera todas las `embedding_<modelo>_<dim>`).
- **Escritura masiva.** `POST /data/batch` escribe nodos y relaciones en **una transacción** (todo o nada), con modos
  `replace`, `ensure` y `merge`, y `replace_from` (borra antes lo que cuelga de un nodo por composición).
- **Avance.** `GET /data/progress/parsing` y `/data/progress/chunking` cuentan, sobre lo guardado, qué está hecho y qué
  falta con una huella dada, y listan los `sha256` por páginas.
- **Vectores.** `data` crea el índice que `embeddings` le pide (`PUT /data/vectors/indexes/{name}`, coseno sobre una
  propiedad `embedding_<modelo>_<dim>` de `FRAGMENTOS` o `EXP_EMBED`) y corre la búsqueda; ningún modelo ni dimensión
  está escrito en `data`. Neo4j admite **un** índice vectorial por etiqueta y propiedad: con el modelo en el nombre de
  la propiedad (055), cada modelo tiene el suyo. Ese nombre es el único que no es constante y se concatena en Cypher:
  `repository/cypher.vector_property` lo valida contra el patrón de `schema/vector_rules.py` (si no, `GraphError`).
  `DELETE /data/vectors/indexes/{name}?drop_property=true` quita también los vectores. `repository/maintenance.py`
  (`VectorMigration`) mueve los vectores de antes de la 055; la corre `prueba-chunking migrate-vectors`.

El grafo completo:

```
Archivos, parseo y chunking oficial
(:PIAA)-[:ES]->(:JSON)-[:VIENE_DE]->(:RAW)
(:JSON)-[:TIENE_SECCION]->(:SECCION)-[:TIENE_FRAGMENTO]->(:FRAGMENTOS)
(:JSON)-[:TIENE]->(:HALLAZGOS)-[:DE_TIPO]->(:ANTIPATRON)-[:INCUMPLE]->(:NORMA);  (:HALLAZGOS)-[:EN]->(:FRAGMENTOS)
(:FACULTAD)-[:PERTENECE]->(:PROGRAMA)-[:HACE_PARTE]->(:ASIGNATURA)-[:PERTENECE]->(:PIAA)
(:CHAT)-[:GENERA]->(:CONSULTA)-[:SOBRE]->(:JSON);  (:CONSULTA)-[:RESPONDIDA_CON {puntaje, orden}]->(:FRAGMENTOS)

Laboratorio
(:EXPERIMENTO)-[:EXP_USA]->(:JSON)
(:EXPERIMENTO)-[:EXP_GENERA]->(:EXP_SECCION)-[:EXP_TIENE_CHUNK]->(:EXP_CHUNK)
(:EXP_EMBEDDINGS)-[:EXP_USA]->(:EXPERIMENTO)
(:EXP_CHUNK)-[:EXP_TIENE_VECTOR]->(:EXP_EMBED {embedding_<modelo>_<dim>})<-[:EXP_GENERA_VECTOR]-(:EXP_EMBEDDINGS)   (055)
(:CONSULTA {laboratorio: true})-[:RESPONDIDA_CON]->(:EXP_CHUNK)      (048: una pregunta con `against`)

Pipeline
(:PIPE_CORRIDA)-[:PIPE_DE]->(:PIPELINE)
(:PIPE_CORRIDA)-[:PIPE_TIENE_ITERACION]->(:PIPE_ITERACION)-[:PIPE_USA]->(:EXPERIMENTO | :EXP_EMBEDDINGS)
(:PIPE_CORRIDA)-[:PIPE_TIENE_EVENTO]->(:PIPE_EVENTO)

Sueltos: CONFIG_OFICIAL (activa = chunking, embeddings = embeddings, llm = llm, consultas = consultas),
CORRIDA_PARSEO, CORRIDA_CHUNKING, CORRIDA_EMBEDDINGS (el historial de cada módulo, que sobrevive al reinicio)
```

`CHAT` y `CONSULTA` los escribe `consultas` desde la 048 (`GENERA` es de composición: borrar un chat borra sus
consultas, nunca los fragmentos citados); `SOBRE` sigue sin uso.

Quedan en el esquema, de antes de la 043, `EXP_DOCUMENTO`, `EXP_PUNTUACION`, `EXP_TIENE_SECCION`,
`EXP_TIENE_PUNTUACION` y `(:JSON)-[:VIENE_DE]->(:EXP_DOCUMENTO)`: ya nadie los escribe (la parte b de la 055 volverá
a usar `EXP_DOCUMENTO` como nodo intermedio por experimento y documento).

`EXP_TIENE_VECTOR` y `EXP_GENERA_VECTOR` son de composición: borrar un experimento de embeddings (`replace_from` su
`EXP_EMBEDDINGS`) se lleva solo sus `EXP_EMBED`; borrar un chunk, sus vectores. Un `FRAGMENTOS` guarda una propiedad
por modelo (`embedding_<modelo>_<dim>`) y su `JSON`, `huella_embedding_<m>_<d>` y `limite_tokens_embedding_<m>_<d>`.

## parsing por dentro (feature 042)

- **Configuración fija** en `config/docling.py` (`PARSING`, `PARSING_VERSION`): tablas en modo `accurate`, jerarquía
  de títulos en PDF, títulos romanos en Word, OCR (RapidOCR con `onnxruntime`) solo en las páginas que sin él quedan
  sin texto, `document_timeout` de 600 s, CPU. Nada se pide por petición: `GET /parsing/config` la muestra. La
  **huella** (`fingerprint_parseo`) es la versión de Docling + `PARSING_VERSION` + la configuración: lo parseado con
  la misma huella se salta.
- **Dominio**: `ParsingRunner` (por cada `sha256`, en orden y una vez: sin `RAW` → `missing`; ya parseado → `skipped`;
  si no, parsea, reanudando un `parcial`), `Check` (qué falta), `ParsedGraph` (el lote `PIAA → JSON → RAW`; `PIAA` con
  `ensure`, nunca `000000`) y `codec` (gzip + base64 del `DoclingDocument`).
- **Vista previa** (048 fase 2): `POST /parsing/preview` lee un pdf/docx/doc (JSON con base64 o multipart con `file`)
  con la misma configuración y responde su texto por secciones; **no guarda nada**. De a una (`PreviewSlot`, 409 si
  otra corre), con `PREVIEW_MAX_BYTES` (20 MiB), `PREVIEW_MAX_PAGES` (30) y `PREVIEW_TIMEOUT` (180 s, 504). Corridas y
  vistas previas comparten los convertidores y convierten de a uno (un lock en `DoclingParser`).
- **Adaptadores**: `docling_parser.py` (`DoclingParser`: primera pasada sin OCR, segunda solo con las páginas sin
  texto), `roman_titles.py`, y el cliente y los stores de `data`.
- **Errores**: `ParseError` es culpa del documento (se anota en su `RAW`, `estado_parseo: error`, y la corrida sigue;
  un `JSON` bueno se conserva); `ParserUnavailable` y `SinkError` son de la máquina o de `data` y cortan la corrida sin
  escribir. Parsear de nuevo un documento borra sus chunks oficiales (`replace_from` el `JSON`): ya no corresponden.

## chunking por dentro (features 043 y 045)

- **Configuración**: `config/docling.py`. Configurable (en un experimento y en la configuración activa): `chunker`
  (`hybrid`, `hierarchical`, `page`), `tokenizer` (de `TOKENIZERS`), `max_tokens` y `merge_peers` (solo `hybrid`; con
  otro chunker, 422). Lo que no viene toma `CHUNKING_DEFAULT` (`hybrid`, MiniLM multilingüe, 126 tokens). Fijo
  (`CHUNKING_FIXED`, `CHUNKING_VERSION`): tablas en tripletas, solo la capa `body`, imágenes por su pie, sin formato,
  títulos delante (`texto_contextualizado`, sobre el que se cuentan los tokens).
- **Configuración activa**: un nodo `CONFIG_OFICIAL` (`activa`) con su `origen` (`defecto`, `experimento`, `manual`).
  Se cambia con `PUT`/`PATCH`/`DELETE /chunking/config` o con `POST /chunking/experiments/{id}/apply`. Cambiarla no
  reprocesa nada.
- **Modelos** (`models/`): `concepts.py` (`ChunkingParameters` y su `fingerprint`, `chunked_fingerprint` = parámetros
  + parseo, `ActiveConfig`, `ParsedDocument`, `Section`, `Chunk`), `requests.py`, `results.py` (`ChunkingRun`,
  `RunStatus`, `ExperimentStatus`...), `batch.py`, `stored.py` (un `TypedDict` por forma guardada, para que una
  propiedad mal escrita sea un error de mypy de los dos lados) y `ports.py` (`DocumentStore`, `MissingDocuments`,
  `ExperimentStore`, `ConfigStore`, `RunStore`, `Chunker`).
- **Dominio** (`domain/`): `parameters.py` (`Parameters.resolve`/`active`), `sections.py` (los chunks agrupados por
  sus títulos), `stats.py`, `production/` (`RunRunner`: recorre la lista de la corrida y, justo antes de chunkear cada
  documento, salta el ya hecho con la misma `huella_chunking`; `OfficialGraph`: el lote bajo el `JSON`, con
  `replace_from`; `RunGraph`: el `CORRIDA_CHUNKING`) y `experiments/` (`ExperimentRunner`, con `pending` para retomar;
  `ExperimentGraph`).
- **Estados**: corridas y experimentos terminan `finished`, `partial` (algún documento falló), `failed` (se cortó) o
  `interrupted` (el servidor se apagó). Los tres últimos se retoman con `POST .../resume` (una corrida, solo si la
  configuración activa no cambió).
- **Adaptadores**: `docling_chunkers.py` (`DoclingChunkers`: un chunker por parámetros y un tokenizador por nombre,
  reusados; tokenizadores en `.cache/tokenizers`), `data/` (clientes, mappers y los stores) y `session.py`.

## embeddings por dentro (features 046 y 055)

El único módulo que carga modelos de vectores. Lee `JSON → SECCION → FRAGMENTOS` (corridas) o `EXPERIMENTO →
EXP_SECCION → EXP_CHUNK` (experimentos) y escribe los vectores con `merge`: en `FRAGMENTOS.embedding_<modelo>_<dim>`
(un `FRAGMENTOS` conserva los de los otros modelos) o en un `EXP_EMBED` por experimento de embeddings y chunk. El
único `replace_from` es borrar un experimento (su `EXP_EMBEDDINGS`). Detalle y desvíos
de lo planeado: [guia-embeddings.md](guia-embeddings.md).

- **Modelos**: `config.MODELS` es la única lista (`ModelSpec`: dimensiones, `default_tokens`, `max_tokens`; los límites
  cuentan los 2 tokens especiales; `pooling`; prefijos de pregunta y de pasaje). Además del MiniLM multilingüe (el
  activo por defecto), los candidatos de la 055: `intfloat/multilingual-e5-base` (768; `query: `/`passage: `) y
  `BAAI/bge-m3` (1024; pooling CLS). Configuración activa en `CONFIG_OFICIAL` (`embeddings`).
- **Cambiar de modelo sin cortar el chat** (055): `POST /embeddings/runs {model}` embebe al lado del activo, `PUT
  /embeddings/config` lo vuelve activo y `DELETE /embeddings/models/{name}/vectors` quita los del viejo (409 si es el
  activo). `GET /embeddings/models?documents=true` cuenta los documentos de cada modelo.
- **Pendiente**: `TOKENIZERS` de chunking solo admite los MiniLM, así que un par de laboratorio con e5 o bge-m3 lo
  rechaza chunking; y el prefijo `passage: ` de e5 cuenta tokens que chunking no conoce (un chunk cortado en
  límite − 2 puede pasarse y fallar su documento).
- **Dominio**: `Runner` (huella por documento; lo que no cambió queda `unchanged`), `ExperimentRunner`, `token_limit`,
  `indexes.py` (la propiedad, el índice `vec_<etiqueta>_<modelo>_<dim>` y las claves de huella salen del modelo). Un chunk más largo que el límite hace fallar su
  documento: nunca se trunca. `UpstreamDown` corta la corrida; `DocumentError`, solo el documento.
- **Adaptadores**: `text_embedder.py` y `local_models.py` (un modelo cargado una vez, caché `.cache/embeddings`) y
  `data/` (cliente, mappers, stores).
- **Registro**: `CORRIDA_EMBEDDINGS` y `EXP_EMBEDDINGS -[:EXP_USA]-> EXPERIMENTO`.
- **Texto → vector** (048): `POST /embeddings/vectors {texts, model?, max_tokens?}` (hasta 64 textos) con el modelo
  activo, o con otro servido (el de un experimento). Un texto más largo que el límite se corta (es una pregunta, no un
  documento). La respuesta trae el nombre del índice de `FRAGMENTOS` y el de `EXP_EMBED` de ese modelo, para que quien
  busca use el índice del mismo modelo. La búsqueda ya no está aquí (`POST /embeddings/search` se quitó): es de
  `consultas`.

## llm por dentro (feature 047)

El único que habla con Ollama; sin estado propio salvo la configuración activa (no guarda conversaciones).

- **Modelos**: `config.MODELS` es la lista de los admitidos (`ModelSpec(context, vision)`): `qwen2.5:0.5b`,
  `llama3.1:8b` (`DEFAULT_MODEL`) y `qwen2.5vl:3b` (visión). Un modelo nuevo es una línea; Ollama puede tener otros,
  pero un modelo no admitido da 422. `llama3.1` y `llama3.1:latest` son el mismo (`domain/names.py`).
- **Configuración activa** en `CONFIG_OFICIAL` (`llm`): `model`, `temperature`, `num_ctx`, `max_tokens` (de la
  respuesta, el `num_predict` de Ollama) y `system`. Si la guardada ya no sirve (su modelo dejó de estar admitido), se
  usa la de por defecto.
- **Dominio**: `settle` (lo pedido sobre la activa, validado: modelo admitido, rangos, `num_ctx` dentro del contexto
  del modelo, imágenes solo con visión y en base64, como mucho `MAX_IMAGES`), `resolve`/`usable`, `replaced`/`patched`.
- **Adaptadores**: `ollama_client.py` (`OllamaClient`: `/api/version`, `/api/tags`, `/api/pull` con su avance línea a
  línea, `/api/delete`, `/api/chat` con `stream: false`). Ollama caído, con timeout o sin el modelo descargado →
  `ModelsDown` (503, con el `ollama pull` que lo arregla); un 400 de Ollama → `InvalidChat` (422). Nunca un 500 por
  Ollama. Un cliente por petición: si Ollama vuelve, la siguiente llamada ya funciona. `data/` guarda la
  configuración.
- **Descargas**: `POST /llm/models/pull` en una fila propia (`WorkQueue`, de a una, hasta `MAX_WAITING`), con su
  registro en memoria (`PullRegistry`, solo de esta sesión) y en `/processes`.

## consultas por dentro (feature 048)

Un consumidor, como el pipeline: llama a `embeddings`, `data` y `llm` (y a `parsing` para los documentos adjuntos) por HTTP (`adapters/session.py`:
`HttpModules`, un `httpx.Client` para toda la app). No tiene procesos ni colas: cada pregunta es una petición.

- **Dominio**: `Asker.search` (vector de la pregunta → `POST /data/vectors/search`, sin LLM ni `min_score`) y
  `Asker.ask` (busca, se queda con los que pasan `min_score`, arma los mensajes con los últimos `history` turnos del
  chat y el prompt con `{context}` y `{question}`, pide la respuesta a `llm` y guarda todo en **un** lote: la pregunta,
  su respuesta y sus citas se guardan juntas o no se guarda nada). `prompt.py` numera los fragmentos como los cita la
  respuesta (`[1]`, `[2]`...); `records.py` arma el lote.
- **`against`** (laboratorio): `{embeddings_experiment}` busca en los `EXP_CHUNK` de ese experimento de embeddings
  (404 si no existe, 409 si no terminó), con su modelo; la consulta y su chat quedan `laboratorio: true` y un chat de
  un tipo no se sigue con preguntas del otro (409). `llm` en el cuerpo cambia el modelo o la temperatura solo para esa
  pregunta.
- **Adjuntos** (fase 2, `domain/attachments.py`): `attachments` en `/ask` y `/search`. Un documento se lee con
  `POST /parsing/preview`, se corta en trozos del tamaño del modelo de embeddings y cada trozo busca; una imagen la
  describe un modelo de visión de `llm` (`VISION_MODEL` `qwen2.5vl:3b`, u otro de visión descargado; ninguno →
  `NoVisionModel`, 503) y su descripción busca; las búsquedas se unen por el mejor puntaje. Límites `MAX_ATTACHMENTS`
  (4), `MAX_ATTACHMENTS_BYTES` (20 MiB), `MAX_PIECES` (48). Nada de los adjuntos se guarda: la `CONSULTA` anota solo
  sus nombres, tipos y cuántos caracteres buscaron.
- **Configuración activa** en `CONFIG_OFICIAL` (`consultas`): `k` (5), `min_score` (0.3), `prompt`, `history` (3).
- **Errores**: un módulo caído → 503 diciendo cuál; lo que `llm` o `embeddings` no admiten → 422; `data` rechaza →
  502.
- **CLI**: `prueba-chunking ask "pregunta"` (`server/ask.py`; `--k`, `--chat`, `--experiment`, `--attach`, `--url`, `--sources`,
  `--timeout`): llama a `POST /consultas/ask` de un servidor que ya corre y muestra la respuesta con sus fuentes, en
  español. No arranca nada.

## pipeline por dentro (features 028 y 044)

- **Plantillas** (`PIPELINE`): etapas en orden. Una etapa es una tarea (`task`, una acción del catálogo), la espera de
  un actor (`external`) o un ciclo (`cycle`) que se repite hasta que su actor aprueba (`max_iterations`). Cada acción
  declara `needs`/`gives` (artefactos) y `Order.check` rechaza con 422 un orden en que a una etapa le falta algo.
- **Las dos incorporadas** (`domain/templates.py`, no se borran):
  - `produccion`: `ingestar` (`ingesta.run`) → `parsear` (`parsing.parse_all`) → `chunkear` (`chunking.promote`,
    `POST /chunking/runs`) → `embeber` (`embeddings.embed`). `scope: "new"` procesa lo recién parseado; `"all"`, todo
    lo parseado (cada módulo salta lo hecho con la misma huella).
  - `laboratorio`: `seleccionar` (`ingesta.chunkable`: congela un lote de `sha256`) → `parsear` (`parsing.parse`) →
    ciclo `laboratorio` con el actor `lab` (`chunking.experiment` → `embeddings.experiment` → `review.score`) →
    `aplicar_chunking` → `aplicar_embeddings` → `aplicar_llm` (`llm.apply`, 050). El pipeline une el par: el
    tokenizador de chunking es el modelo de embeddings y `max_tokens` cabe en el límite del modelo menos 2
    (`domain/pairing.py`).
- **El trío** (050): `params` del ciclo puede traer también `llm` (`{model, temperature, num_ctx, max_tokens,
  system}`), validado contra `GET /llm/models` antes de lanzar y en cada `retry` (422 si el modelo no está admitido y
  descargado, o `num_ctx` pasa su contexto). La iteración lo guarda (`PIPE_ITERACION.config_llm`) y la bandeja de `lab`
  lo trae (`llm`), para que evalúe con `POST /consultas/ask {against, llm}`. Al aprobar, `aplicar_llm` hace
  `PUT /llm/config` con el de la iteración aprobada; sin `llm` en el ciclo no hace nada. Un `retry` cuyo `next` solo
  cambia `llm` reutiliza los experimentos de la iteración anterior (`PIPE_ITERACION.reutiliza`): sus etapas quedan
  registradas como reutilizadas, sin volver a chunkear ni embeber.
- **Corrida** (`PIPE_CORRIDA`, con una copia de la plantilla): `queued`, `running`, `waiting`, `done`, `failed`,
  `cancelled`, `interrupted`. `domain/engine.py` es la máquina de estados, sin HTTP; `api/executor.py` tiene un
  trabajador por módulo (`QUEUES`), espera los 409 de una fila llena (`BUSY_RETRY`) y sondea cada trabajo hasta que
  termina. Las esperas de un actor no ocupan hilo.
- **Actores**: `GET /pipeline/inbox?actor=`, aviso opcional a su `callback_url` (solo hosts permitidos) y respuesta
  con `.../decision` (ciclo: `retry` con `next`, o `approve`) o `.../complete`. La puntuación del par queda en la
  iteración.
- **Adaptadores**: un cliente por módulo (`ingesta_client.py`, `parsing_client.py`, `chunking_client.py`,
  `embeddings_client.py`, `llm_client.py`, `data_client.py`), sobre `adapters/http/jobs.py` (lanzar y esperar), y
  `run_store.py`.

## server

`src/server/` crea una `FastAPI` raíz y **monta** (`app.mount`) la app de cada módulo bajo su prefijo. Montar conserva
los manejadores de error y el `/docs` de cada uno. Abre el adaptador de Neo4j una vez y lo cierra al apagar. Si falta
la clave o el driver, `data` se monta sobre un grafo «no disponible» (`UnavailableGraph`) que responde 503; si Neo4j
solo no responde todavía (Docker arrancando), sobre un `ReconnectingGraph` (054) que reintenta al usarse, como mucho
cada `RECONNECT_EVERY` (5 s), y pasa a ser el real cuando Neo4j responde, sin reiniciar nada. Suma `GET /health`
(estado de cada módulo), `GET /processes` y el WebSocket `/processes/ws` (los procesos de todos), y las guardas
`HostGuard` (solo los hosts servidos) y `BodyLimit` (32 MiB por defecto). No hay autenticación: escucha en
`127.0.0.1`. Ver [api.md](api.md).

La CLI (`prueba-chunking`, `server/cli.py`) tiene cuatro comandos: la **consola** (por defecto), `serve` (solo el
servidor; nunca toca Docker), `ask` (una pregunta a un servidor que ya corre) y `migrate-vectors` (055,
`server/migrate.py`: mueve una vez los vectores de antes de la 055, directo sobre Neo4j, con el servidor parado;
`--simulate` solo cuenta; vive en `server` porque necesita a `data` y a `embeddings`). `--ollama-url` (o `OLLAMA_URL`, por
defecto `http://127.0.0.1:11434`) dice dónde está Ollama, para `/llm`.

## La consola

`src/server/console/` (features 034 a 039): menús en la terminal, en español, con asciimatics. Habla **solo HTTP** con
el servidor: no importa ningún módulo.

- Al arrancar (feature 054, `docker_services.py`), si Neo4j o Ollama no responden y son locales, los levanta con
  `docker compose up -d` del proyecto `prueba-chunking` (`docker/compose.yaml` + `docker/compose.<gpu>.yaml`; `--gpu
  amd` —ROCm, por defecto—, `nvidia` o `cpu`, o `OLLAMA_GPU`) y espera a que Neo4j acepte el handshake de bolt (a
  Ollama no lo espera). Si el demonio de Docker no responde, lo dice y reintenta cada segundo hasta 5 minutos. Pasa el
  contenedor suelto de antes (`prueba-chunking-neo4j`) al compose sin perder su volumen (si está detenido; si corre,
  avisa). Después arranca **su propio servidor** (`python -m server serve`, salida en `.cache/console-server.log`), que
  vive exactamente lo que la consola, y baja en segundo plano los modelos de `llm` que falten (`model_pulls.py`, con su
  avance en el inicio).
- Al salir detiene (`docker compose stop`) **solo lo que arrancó ella**; con `--keep-docker`, nada. Si muere sin
  limpiar (incluso `kill -9`), `docker_watchdog.py`, un proceso aparte que espera en una tubería, lo detiene igual.
- Los menús salen del `openapi.json` de cada módulo (`catalog.py`): inicio (módulos con su estado) → módulo → recurso
  (primer tramo de la ruta) → acción → formulario → respuesta. Lo curado a mano (nombres en español, cuerpos de
  ejemplo, progreso, autocompletado, guías) está en `texts.py`, `bodies.py`, `progress.py`, `suggestions.py` y
  `forms.py`. Ver [guia-consola.md](guia-consola.md).
- Pantallas propias: procesos en vivo (`/processes/ws`), esquema de `data` dibujado, avance de parseo y chunking
  (`coverage.py`, de `/data/progress/*`) y el editor de plantillas del pipeline como diagrama de flujo.
- Lo que la consola no puede enviar aparece bloqueado con su motivo: `POST /ingesta/uploads` (049) necesita un cuerpo
  multipart con archivos, así que se sube desde la API o el front.

## Planificado

Lo que sigue (ver [roadmap](../spec/constitution/roadmap.md)). Hechas: 047 (`llm`), 048 (`consultas`, con adjuntos),
049 (subidas), 050 (el trío en el laboratorio), 054 (Neo4j + Ollama en Docker Compose) y 055 parte a (vectores por
modelo). **Lo de esta tabla no existe todavía.**

| Feature | Qué | Encaje |
|---|---|---|
| [055 · parte b](../spec/features/055-grafo-de-experimentos-y-vectores/spec.md) | `EXP_DOCUMENTO` intermedio por experimento y documento; 409 al borrar un experimento con dependientes (después de commitear la 045) | data + chunking |
| [051 · acceso por cliente](../spec/features/051-acceso-por-cliente/spec.md) | tokens por cliente y rutas permitidas (`ClientGuard`) | server |
| [052 · frontend web](../spec/features/052-frontend-web/spec.md) | chat con fuentes y carga de documentos | aparte, en `web/`, solo HTTP |
| [053 · contrato del laboratorio](../spec/features/053-contrato-laboratorio/spec.md) | qué rutas usa el actor `lab` y en qué orden | documentación + lo que falte |

## Convenciones que valen para todo

- **Código en inglés; datos guardados en español.** Identificadores, docstrings, mensajes, CLI y claves JSON nuevas en
  inglés. Siguen en español lo ya guardado o publicado: tablas y columnas de la memoria, valores de `Category`, claves
  JSON de ingesta y de `/stats`, carpetas, etiquetas, tipos, propiedades y valores de estado del grafo. La interfaz de
  la consola, en español.
- **Tipos estrictos.** mypy `strict`, sin `Any` fuera de los adaptadores, sin `dict`/`list` sin parámetros, sin
  `# type: ignore`. Datos en dataclasses `frozen=True`.
- **`__init__.py` reexporta lo público** y se importa por paquete con ruta absoluta (`from chunking.domain import …`).
- **Fallo de la máquina ≠ fallo del documento.** Lo primero corta la corrida sin escribir; lo segundo falla solo ese
  documento, se anota y la corrida sigue (reglas de calidad de la feature 040, en
  [tech-stack.md](../spec/constitution/tech-stack.md)).
- **Spec Driven Development.** Antes de tocar código: `spec/constitution/` y la carpeta de la feature
  (`spec/features/NNN-*/` con `spec.md`, `plan.md`, `tasks.md`).

## Cómo se valida un cambio

```bash
uv run ruff format && uv run ruff check   # formato y lint
uv run mypy                               # tipos (strict)
uv run pytest                             # tests, sin servidor ni red (httpx.MockTransport, puertos falsos)
uv run pytest --cov                       # como el CI: falla bajo el piso fail_under de pyproject.toml
```

Marcadores: `integration`, `docling` (Docling o docling-core de verdad), `embed` (el modelo de vectores de verdad),
`neo4j` (solo con `NEO4J_TEST_URL`) y `ollama` (solo con `OLLAMA_TEST_URL` y el modelo `qwen2.5:0.5b`); se omiten
solos si falta lo que usan.

Además, según lo que se toque:

- **ingesta:** `POST /ingesta/runs {"simulate": true}` y `GET /ingesta/stats` sobre una **copia** de la memoria,
  antes y después; deben quedar iguales salvo la fecha. Nunca sobre `data/ingesta/.memoria.sqlite3` directamente (ver
  [guia-ingesta.md](guia-ingesta.md)).
- **data, parsing, chunking, embeddings, llm, pipeline, consultas:** Neo4j de prueba en Docker (y Ollama, para `llm` y
  `consultas`) y los archivos de `http/` (ver
  [api.md](api.md#probar-con-los-archivos-http)).

Ojo: `uv sync` a secas desinstala los extras; nombrar siempre los que se usan.
