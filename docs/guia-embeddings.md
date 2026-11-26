# Guía: el módulo `embeddings`

Paso a paso para montar un módulo nuevo, **`embeddings`**, que sea **el único lugar del proyecto que calcula vectores**:

1. Trae lo que hace la carpeta `embeddings/` de [piaa-rag](https://github.com/jeronimo-taborda-e/piaa-rag/tree/master):
   embeber los fragmentos oficiales, guardarlos en Neo4j y buscar por similitud (Parte A).
2. Se queda con el código del modelo de vectores que hoy vive en `chunking` (`_Embedder`, de la estrategia `semantic`).
   `chunking` no lo necesita más: la feature 043 quita sus estrategias propias, `semantic` incluida (Parte B).
3. Lo conecta con la consola, el pipeline, los tests y la documentación (Parte C).

**No se copia el código tal cual.** `piaa-rag` es un conjunto de scripts que leen un `.jsonl` y hablan directo con
Neo4j. Aquí eso no está permitido: los módulos no se importan entre sí, solo `data` toca el grafo y las reglas de negocio
no hacen I/O. Por eso hacen falta archivos y funciones intermedias, y cada paso dice cuáles.

**Qué se comprobó:**

- Contra un Neo4j 2026.07.1 temporal: crear el índice vectorial con el nombre **y** las dimensiones como parámetros
  (`CREATE VECTOR INDEX $name …`), la consulta de A6 filtrada por `estado_chunking` y que repetir el índice no cambia
  nada (`tests/data/repository/test_vector_repository.py`, `-m neo4j`).
- Con el modelo real (`-m embed`): 384 dimensiones, norma 1, 512 posiciones (`max_tokens`).
- De punta a punta con el servidor: corrida, repetición (`unchanged`), búsqueda, experimento, `apply`, historial tras
  reiniciar, borrado y el cliente del pipeline (`EmbeddingsClient`) contra el módulo en vivo.

## Implementado (feature 046): en qué se apartó de esta guía

La guía se siguió paso a paso; donde chocaba con las reglas actuales del proyecto, ganaron las reglas:

| Guía | Implementación | Por qué |
| --- | --- | --- |
| Corridas y experimentos solo en memoria | En data: `CORRIDA_EMBEDDINGS` y `EXP_EMBEDDINGS -[:EXP_USA]-> EXPERIMENTO`, con `detalle` (JSON); `GET` responde también las de antes de reiniciar | Feature 041 (historial tras reinicio), como parsing; el pipeline enlaza el experimento con `PIPE_USA` (`EMBEDDINGS_EXPERIMENT_LABEL = "EXP_EMBEDDINGS"`) |
| Etiquetas como texto en `config` | `GraphLabel`/`GraphRelation` en `models/batch.py`; el dominio arma un `GraphBatch` y el adaptador lo traduce | Como parsing y chunking; un test las compara con el esquema de data |
| `GET /models` sin `default`; experimento sin `description` | `ServedModel.default` y `NewExperiment.description` | Es lo que envía y lee el pipeline (044) |
| Estados `queued/running/finished/failed` | Más `interrupted` y `cancelled`; `DELETE /runs/{id}` saca de la fila | Como parsing |
| Vectores de experimento sin dueño | `EXP_CHUNK.experimento_embedding`: borrar un experimento quita solo sus vectores | Dos experimentos pueden embeber los mismos chunks |
| `embedded`: solo lo recalculado | También lo `unchanged` (ya tiene vectores) | Es lo que el pipeline pasa a la etapa siguiente |
| Un experimento de chunking cualquiera | Debe estar `finished` (409 si no) | Sus chunks ya no cambian |
| `db.index.vector.queryNodes` | Igual, aunque Neo4j 2026 lo marca obsoleto | `SEARCH` no acepta el índice como parámetro |
| «Otro modelo, otro índice» sobre `embedding` | Un índice por etiqueta: otro modelo sobre `FRAGMENTOS` (o `EXP_CHUNK`) da 409 nombrando el que ocupa la propiedad; `DELETE /data/vectors/indexes/{name}` lo quita | Neo4j admite **un** índice vectorial por etiqueta y propiedad (`IndexAlreadyExists`); con `IF NOT EXISTS` lo ignoraba en silencio |

Consola: módulo «embeddings», servicio «vectores» (bloquea lo que embebe sin `torch`), plantillas, progreso y
autocompletado. `http/embeddings/`, `http/data/vectors.http` y `http/connections/embeddings-data.http`.

## Cambios por la feature 048 (parte 1): la búsqueda pasó a `consultas`

Con el RAG (`src/consultas/`, feature 048), `embeddings` queda en **texto → vector**; buscar es de `consultas`, un
consumidor que sí puede llamar a otros módulos. Lo que dice esta guía sobre `POST /embeddings/search` (A8, el
`search.py` de A8, C2, C4 y C5) **ya no vale**:

| Antes (046) | Ahora (048) |
| --- | --- |
| `POST /embeddings/search {question, k}`: vectoriza y llama a `POST /data/vectors/search` | **Se quitó.** La búsqueda es `POST /consultas/search {question, k, against?}` (sin LLM) y `POST /consultas/ask` (con la respuesta del LLM y sus fuentes) |
| `POST /embeddings/vectors` «se quita» (A8) | **Volvió**, con otro uso: `POST /embeddings/vectors {texts, model?, max_tokens?}` (1 a `MAX_TEXTS` = 64 textos de hasta 20 000 caracteres) → `{model, max_tokens, dimensions, index, experiment_index, vectors}`, en `api/routes/vectors.py`. Con el modelo activo, o con `model` (otro servido: el de un experimento de embeddings, para preguntarle a ese experimento) |
| Un texto más largo que el límite hace fallar su documento | Sigue igual para los documentos (`runs`, `experiments`); en `/vectors` **se corta**: es una pregunta, no un documento |
| El índice lo decidía la ruta de búsqueda | `/vectors` devuelve los nombres de los índices de ese modelo (`index` de `FRAGMENTOS`, `experiment_index` de `EXP_CHUNK`, `vec_<etiqueta>_<modelo>_<dim>`): quien busca usa el del mismo modelo que vectorizó la pregunta |
| `POST /data/vectors/search {index, vector, k}`: solo `FRAGMENTOS` | Acepta `experiment` (el id de un experimento de embeddings): con él, el índice debe ser de `EXP_CHUNK` y solo entran los `EXP_CHUNK` con `experimento_embedding` igual a ese id (`VectorRepository.search_experiment`); cada fila trae `{id, score, text, headings, pages, sha256, origin, code}` |
| `http/embeddings/search.http` | `http/embeddings/vectors.http`; las búsquedas, en `http/consultas/` y `http/connections/consultas.http` |

La regla de los módulos no cambia: `embeddings` sigue sin nombrar rutas de otro módulo que no sea `/data`
(`tests/common/test_module_rule.py`); quien llama a `/embeddings/vectors` es `consultas`. En la consola, `POST /vectors`
también queda bloqueado sin el servicio «vectores», y `consultas ▸ búsqueda`/`preguntar` también lo necesitan.

## Cambios por la feature 055 (parte a): un vector y un índice por modelo

Neo4j admite **un** índice vectorial por etiqueta y propiedad. Con todos los vectores en `embedding`, solo cabía un
modelo por etiqueta y cambiar de modelo cortaba el chat (borrar el índice, reembeber). Desde la 055 el nombre de la
propiedad lleva el modelo y sus dimensiones, así que cada modelo tiene la suya y su índice, y conviven. Lo que dicen
A2–A8 sobre `embedding`, `huella_embedding`, `limite_tokens_embedding` y `EXP_CHUNK.experimento_embedding` **ya no
vale**:

| Antes (046/048) | Ahora (055) |
| --- | --- |
| `FRAGMENTOS.embedding` (+ `modelo_embedding`, `version_embedding`) | `FRAGMENTOS.embedding_<modelo>_<dim>`, una por modelo (p. ej. `embedding_paraphrase_multilingual_minilm_l12_v2_384`: el modelo sin su dueño, en minúsculas y `[a-z0-9_]`). Los lotes siguen en `merge`: embeber con un modelo no toca los vectores de los otros |
| `JSON.huella_embedding`, `JSON.limite_tokens_embedding` | `huella_embedding_<m>_<d>` y `limite_tokens_embedding_<m>_<d>` (`domain/indexes.py`: `fingerprint_key`, `limit_key`), más `embebido_en` |
| `EXP_CHUNK.embedding` con `experimento_embedding` | Un nodo `EXP_EMBED {id: <experimento de embeddings>:<chunk>, modelo, version_embedding, embedding_<m>_<d>}` por experimento y chunk: `(:EXP_CHUNK)-[:EXP_TIENE_VECTOR]->(:EXP_EMBED)<-[:EXP_GENERA_VECTOR]-(:EXP_EMBEDDINGS)`, las dos de composición. Dos experimentos con modelos distintos sobre los mismos chunks ya no se pisan; borrar un experimento es `replace_from` su `EXP_EMBEDDINGS` (el único `replace_from` del módulo) |
| Un índice `vec_<etiqueta>_<modelo>_<dim>` sobre `embedding`; otro modelo en la misma etiqueta daba 409 | `vec_fragmentos_<m>_<d>` sobre `FRAGMENTOS.embedding_<m>_<d>` y `vec_exp_embed_<m>_<d>` sobre `EXP_EMBED.embedding_<m>_<d>` (`index_for`, `index_name`); `PUT /data/vectors/indexes/{name}` recibe `{label, property, dimensions}` |
| `data` concatenaba solo constantes en Cypher | La propiedad de vector es el único nombre variable: `data` la valida contra `embedding_[a-z0-9_]{1,120}` (`schema/vector_rules.valid_vector_property`, `repository/cypher.vector_property`; si no, `GraphError`). `data` sigue sin conocer los modelos: los nombres los arma `embeddings` |
| `?omit=embedding` dejaba fuera `embedding` | Deja fuera todas las propiedades de vector (`is_vector_property`, la vieja incluida) |
| `POST /data/vectors/search` con `experiment`: índice de `EXP_CHUNK` | Índice de `EXP_EMBED`, solo los que calculó ese experimento; cada fila sigue siendo el `EXP_CHUNK` (`id`, `text`, `sha256`...). `experiment_index` de `POST /embeddings/vectors` nombra el de `EXP_EMBED` |
| `DELETE /data/vectors/indexes/{name}` | Con `?drop_property=true` quita también esa propiedad de todos los nodos de la etiqueta |
| `MODELS`: solo el MiniLM multilingüe | Más los candidatos para comparar en el laboratorio: `intfloat/multilingual-e5-base` (768, 512 tokens, prefijos `query: ` delante de una pregunta y `passage: ` delante de un chunk, `domain/prefixes.py`; cuentan en sus tokens) y `BAAI/bge-m3` (1024, 8192 tokens, `Pooling.CLS`). El activo por defecto sigue siendo el MiniLM |

Rutas nuevas o cambiadas:

- `POST /embeddings/runs {sha256s, force, simulate, model?}`: con `model` (otro servido), embebe **al lado** del activo.
- `GET /embeddings/models?documents=true`: cada modelo con `documents`, cuántos documentos oficiales tienen sus
  vectores (lee todos los `JSON`: lento; `null` si data no responde). Sin el parámetro no le pregunta a data (el
  pipeline lo llama en cada revisión).
- `DELETE /embeddings/models/{name}/vectors` → `{model, index, index_dropped, documents}`: quita la huella de ese
  modelo de cada `JSON` (por lotes de `FINGERPRINT_BATCH`), su índice de `FRAGMENTOS` y su propiedad. 409 si es el
  activo; los `EXP_EMBED` de los experimentos quedan.

**Cambiar de modelo sin cortar el chat:**

```bash
curl -XPOST localhost:8000/embeddings/runs -H 'Content-Type: application/json' \
  -d '{"sha256s": ["<sha256>", "..."], "model": "BAAI/bge-m3"}'        # 1. vectores del nuevo, al lado del activo
curl 'localhost:8000/embeddings/models?documents=true'                  #    ¿ya tiene todos los documentos?
curl -XPUT localhost:8000/embeddings/config -H 'Content-Type: application/json' \
  -d '{"model": "BAAI/bge-m3"}'                                         # 2. el chat pasa a buscar en su índice
curl -XDELETE localhost:8000/embeddings/models/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2/vectors   # 3. el viejo
```

**Migración de lo guardado antes de la 055.** Una vez, después de actualizar, con el servidor (y la consola) parados
—si no, el chat puede buscar en un índice que se está rehaciendo—:

```bash
NEO4J_PASSWORD=... uv run prueba-chunking migrate-vectors --simulate   # cuenta lo que movería (JSON en stdout)
NEO4J_PASSWORD=... uv run prueba-chunking migrate-vectors              # lo mueve; --neo4j-url/--neo4j-user/--neo4j-database
```

`server/migrate.py` arma los nombres con `embeddings.domain` y se los pasa a `data.repository.VectorMigration`
(`repository/maintenance.py`): vive en `server` porque necesita a los dos. Es idempotente (una segunda corrida no
encuentra nada; una cortada la termina la siguiente) y va por lotes de 1000 nodos: `FRAGMENTOS.embedding` →
`embedding_<m>_<d>`; las huellas y límites del `JSON` → `*_<m>_<d>`; `EXP_CHUNK.embedding` de un experimento que existe →
su `EXP_EMBED`, y el de ninguno se borra; los índices sobre `embedding` se borran y se crea uno por propiedad presente.
El modelo de un vector es su `modelo_embedding` o, si no lo tiene, el activo; sus dimensiones, el largo del vector.
Sale 0 hecho o simulado, 1 si Neo4j falla, 2 sin clave o sin driver.

**Resuelto en la 062:** `TOKENIZERS` de chunking admite también `multilingual-e5-base` y `bge-m3`, y
`GET /embeddings/models` dice por modelo cuántos tokens de su propio tokenizador puede tener un chunk:
`passage_budget` (`max_tokens` − 2 especiales − tokens del `passage_prefix`, contados cargando solo el tokenizador),
`default_passage_budget` (lo mismo sobre `default_tokens`) y `official_passage_budget` (el de defecto dejando lugar a
los `HEADING_TOKENS` del curso cuando no caben en las posiciones del modelo); `null` si el prefijo no se puede contar
(sin el extra `embed`). Con esos números, `chunking.fit` corta para varios modelos a la vez. Un experimento de
embeddings se continúa con `POST /experiments/{id}/resume` (lo chunkeado de su experimento de chunking sin vector de
este; `pending` en su vista) y una corrida con `POST /runs/{id}/resume` (su lista, saltando lo `unchanged`). Desde la parte b de la 055, un experimento de embeddings lee los chunks por
`EXPERIMENTO → EXP_DOCUMENTO → EXP_SECCION → EXP_CHUNK`, y borrarlo da 409 si una corrida del pipeline lo enlaza
(`?force=true` lo borra igual).

## Cómo leer las referencias

Cada paso empieza con un recuadro **Viene de**, que dice de dónde sale lo que se escribe:

- **`piaa-rag`**: enlaces con número de línea al commit
  [`f6368cd`](https://github.com/jeronimo-taborda-e/piaa-rag/tree/f6368cda6c38c10cb035937e71d46145e0b70398), el que se
  revisó. Si el repositorio cambia, los enlaces siguen mostrando esa versión.
- **Este repositorio**: rutas como `src/chunking/adapters/strategies/embeddings.py:10`.

## Estado actual

Hecho (feature 046). Ver «Implementado» arriba para lo que cambió frente a esta guía, «Cambios por la feature 048»
para la búsqueda, que pasó a `consultas`, y «Cambios por la feature 055» para los vectores por modelo.

## Cambios por las features 042, 043 y 044

Esta guía se ajustó a la reorganización de esas features (`spec/features/042-modulo-parseo/`,
`043-chunking-con-docling/`, `044-pipeline-produccion-y-laboratorio/`). Lo que cambia para `embeddings`:

- **Regla de los módulos.** Los módulos de trabajo (`ingesta`, `parsing`, `chunking`, `embeddings`) **no se hablan
  entre sí**; todos leen y escriben en `data`, y **solo el pipeline orquesta**. `embeddings` solo habla con `data`: no
  llama a `chunking` (no hay `GET /chunking/graph` ni `GET /chunking/documents/{sha256}/chunks`) y `chunking` no lo
  llama a él (no hay `POST /embeddings/vectors`).
- **No elige qué procesar.** Recibe listas explícitas que le da el pipeline: los `sha256` de los documentos que
  `chunking` acaba de chunkear (producción) o el id de un experimento de chunking (laboratorio). No hay «todos los
  documentos» ni `limit`: eso lo decide el pipeline.
- **Lee lo guardado en `data`**, no en otros módulos: `FRAGMENTOS` bajo `JSON → SECCION`, o `EXP_CHUNK` bajo
  `EXPERIMENTO → EXP_SECCION`. Los nombres de etiquetas, relaciones y estados son los del esquema de `data`
  (`GET /data/schema`), no los publica `chunking`.
- **Configuración activa y experimentos**, como en `chunking`: `GET`/`PUT`/`PATCH`/`DELETE /embeddings/config` (modelo y
  `max_tokens`), `POST /embeddings/experiments` sobre un experimento de chunking y `POST /embeddings/experiments/{id}/apply`.
  En el laboratorio del pipeline se prueban **juntos** chunking y embeddings; la puntuación es del par y vive en el
  pipeline.
- **El límite de tokens va atado.** El pipeline pone el tokenizador de chunking igual al modelo y `max_tokens` de
  chunking = límite del modelo − 2 (los tokens especiales); a `embeddings` le pasa ese límite + 2.

## El resultado

```
                     pipeline (orquesta; solo pasa ids)
                        │ sha256s chunkeados       │ id de experimento de chunking
                        ▼                          ▼
  POST /embeddings/runs        POST /embeddings/experiments         POST /embeddings/search (048: se quitó)
           │                            │                                  │
           ▼                            ▼                                  ▼
 ┌──────────────────────────── módulo embeddings ────────────────────────────────┐
 │ api → domain (Runner, ExperimentRunner) → puertos → adapters                   │
 │ ÚNICO que carga el modelo (adapters/text_embedder.py)                          │
 └───────────────────────────────────┬────────────────────────────────────────────┘
                                     │ HTTP, solo hacia data
                                     ▼
   GET /data/nodes/...          (lee JSON → SECCION → FRAGMENTOS, o EXPERIMENTO → EXP_SECCION → EXP_CHUNK)
   POST /data/batch             (guarda los vectores con `merge`)
   PUT /data/vectors/indexes/…  POST /data/vectors/search   (rutas nuevas, A6)
                                     │
                                     ▼
                                   Neo4j
```

## Mapa: dónde está cada cosa hoy y adónde va

### Lo que viene de `piaa-rag`

Base de los enlaces: `https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/`.

| En `piaa-rag` (archivo y líneas)                                                                                                                                                          | Qué hace allí                                                    | Qué se hace aquí                                                         | Dónde queda                                                        | Paso   |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- | ------------------------------------------------------------------------ | ------------------------------------------------------------------ | ------ |
| [`embeddings/contract.py` L9-23](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/contract.py#L9-L23)                              | `ChunkIn`: forma de cada línea del `.jsonl`; `text_to_embed`     | **Se reemplaza:** no hay `.jsonl`, los chunks se piden por HTTP          | `models/concepts.py` (`EmbeddableChunk`)                           | A3     |
| [`embeddings/contract.py` L26-49](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/contract.py#L26-L49)                            | `read_chunks`: lee y valida el `.jsonl`, ids repetidos           | **Se reemplaza:** los chunks se leen de `data`                           | `adapters/data/chunks_client.py` (cliente y mapper)                | A7     |
| [`embeddings/adapter.py` L7-32](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/adapter.py#L7-L32)                                | `write_contract`: escribe el `.jsonl` desde un chunker           | **Se descarta:** `chunking` ya guarda en el grafo                        | —                                                                  | —      |
| [`embeddings/llm_models.py` L6-9](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/llm_models.py#L6-L9)                            | Nombres de modelos y `EMBEDDING_VERSION`                         | **Se adapta:** un registro de modelos con dimensiones y límite de tokens | `config/settings.py` (`MODELS`)                                    | A2     |
| [`embeddings/llm_models.py` L12-26](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/llm_models.py#L12-L26)                        | `load_model` (una vez) y `embed` con `sentence-transformers`     | **Se adapta:** `transformers` + `torch`, como ya hace `chunking`         | `adapters/text_embedder.py`, `local_models.py`                     | A5     |
| [`embeddings/llm_models.py` L29-34](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/llm_models.py#L29-L34)                        | `find_long_chunks`: los que el modelo truncará                   | **Se endurece:** avisar no basta, el documento falla                     | `domain/runner.py`                                                 | A4     |
| [`embeddings/load_fragments.py` L26-30](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/load_fragments.py#L26-L30)                | `Q_FINGERPRINTS`: huella guardada de cada fragmento              | **Se adapta:** una huella por documento, en el nodo `JSON`               | `adapters/data/documents_client.py`                                | A7     |
| [`embeddings/load_fragments.py` L32-39](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/load_fragments.py#L32-L39)                | `Q_WRITE`: `MERGE` del fragmento y `SET f += props`              | **Se reemplaza** por `POST /data/batch` en modo `merge`                  | `domain/batches.py`                                                | A4     |
| [`embeddings/load_fragments.py` L41-51](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/load_fragments.py#L41-L51)                | `Q_RETIRE`: borra o marca `obsoleto` los fragmentos viejos       | **Se descarta:** `replace_from` ya borra lo viejo al refragmentar        | — (ver «Decisiones pendientes»)                                    | —      |
| [`embeddings/load_fragments.py` L54-56](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/load_fragments.py#L54-L56)                | `fingerprint`: modelo + versión + texto                          | **Se adapta:** por documento                                             | `domain/fingerprint.py`                                            | A4     |
| [`embeddings/load_fragments.py` L59-137](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/load_fragments.py#L59-L137)              | `main`: argumentos, leer, filtrar sin cambios, embeber, escribir | **Se divide** en API, dominio y adaptadores                              | `api/`, `domain/runner.py`                                         | A4, A9 |
| [`embeddings/search.py` L19-29](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/search.py#L19-L29)                                | `Q_FRAGMENTS`: consulta al índice vectorial                      | **Se mueve a `data`** (solo `data` toca Neo4j)                           | `data/repository/vector_repository.py`                             | A6     |
| [`embeddings/search.py` L38-43](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/search.py#L38-L43)                                | `search`: pregunta → vector → consulta                           | **Se divide:** el vector en `embeddings`, el Cypher en `data`            | `api/routes/search.py`                                             | A8     |
| [`embeddings/search.py` L31-35, L46-49](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/search.py#L31-L49)                        | Búsqueda de imágenes con CLIP                                    | **Se deja fuera**                                                        | Ver «Fuera de esta guía»                                           | —      |
| [`embeddings/load_images.py`](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/load_images.py)                                     | Vacío                                                            | **Se deja fuera**                                                        | Ver «Fuera de esta guía»                                           | —      |
| [`scripts/001_schema.cypher` L66-69](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/scripts/001_schema.cypher#L66-L69)                      | `CREATE VECTOR INDEX fragmento_emb_minilm_v1` (384, coseno)      | **Se adapta:** `embeddings` arma el nombre y lo pide; `data` lo crea     | `embeddings/domain/indexes.py`, `PUT /data/vectors/indexes/{name}` | A6     |
| [`scripts/001_schema.cypher` L71-77](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/scripts/001_schema.cypher#L71-L77)                      | Índices CLIP de fragmentos e imágenes                            | **Se deja fuera**                                                        | —                                                                  | —      |
| [`scripts/001_schema.cypher` L55-64](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/scripts/001_schema.cypher#L55-L64)                      | Índices `FULLTEXT` en español                                    | **Se deja fuera** (mismo patrón que A6)                                  | —                                                                  | —      |
| [`validation/models.py` L56-71](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/validation/models.py#L56-L71)                                | `FragmentoIn`: forma del fragmento con su vector                 | **Se reemplaza** por un `TypedDict`                                      | `models/stored.py`                                                 | A3     |
| [`validation/models.py` L6-10](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/validation/models.py#L6-L10)                                  | `DIM_MINILM = 384`, `VectorMiniLM`                               | **Se adapta:** dimensión en el registro de modelos y en el índice        | `config/settings.py`, `data/schema/`                               | A2, A6 |
| [`docker-compose.yml` L10-11](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/docker-compose.yml#L10-L11)                                    | Memoria de Neo4j (2 GB heap, 1 GB page cache)                    | **Pendiente de medir**                                                   | Ver «Decisiones pendientes»                                        | —      |
| [`requirements.txt`](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/requirements.txt), `.env`, `dotenv`, `argparse`, `GraphDatabase.driver` | Dependencias y conexión                                          | **Se descartan:** lo resuelven `pyproject.toml`, `server` y `data`       | —                                                                  | A1     |

### Lo que hoy está en `chunking`

| Hoy en este repositorio                                                                            | Qué hace                                              | Qué pasa                                                                         | Paso |
| -------------------------------------------------------------------------------------------------- | ----------------------------------------------------- | -------------------------------------------------------------------------------- | ---- |
| `src/chunking/adapters/strategies/embeddings.py` (`_Embedder`)                                     | Mean pooling normalizado con `transformers` y `torch` | Se **copia** a `src/embeddings/adapters/text_embedder.py` (`TextEmbedder`)       | A5   |
| `src/chunking/adapters/strategies/tokens.py:11` (`pretrained`)                                     | Lee un modelo de la caché o lo baja una vez           | Se copia a `text_embedder.py`                                                    | A5   |
| `src/chunking/adapters/strategies/` entera, `semantic.py` incluida                                 | Estrategias propias de chunking                       | **La borra la 043** (chunking solo usa los chunkers de Docling)                  | B    |
| `src/chunking/config/settings.py:25-31` (`EMBEDDING_MODELS`, `EMBEDDING_CACHE`, `EMBEDDING_BATCH`) | Modelos permitidos, caché y lote                      | Pasan a `src/embeddings/config/settings.py`; **la 043 los borra** de `chunking`  | A2   |
| `tests/chunking/adapters/strategies/test_embeddings.py`                                            | Mean pooling                                          | Se copia a `tests/embeddings/adapters/test_text_embedder.py`; la 043 borra el original | C3   |

### Los nombres cambian

| `piaa-rag`                   | Aquí                                                                                   |
| ---------------------------- | -------------------------------------------------------------------------------------- |
| `Fragmento`                  | `FRAGMENTOS`                                                                           |
| `Seccion`                    | `SECCION`                                                                              |
| `Version`                    | `JSON`                                                                                 |
| `texto_con_contexto`         | `texto_contextualizado`                                                                |
| `chunk_index`                | `indice`                                                                               |
| `hash_embedding` (por chunk) | `huella_embedding` (por documento, en `JSON`)                                          |
| `estrategia_chunking`        | No existe en `FRAGMENTOS`. Lo que identifica los parámetros es `fingerprint` en `JSON` |
| Neo4j 5.26, driver `neo4j<6` | Neo4j 2026.07, driver `neo4j>=6.4`                                                     |

## Requisito previo: el límite de tokens es variable

> **Viene de:** [`llm_models.py` L29-34](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/llm_models.py#L29-L34)
> y su uso en [`load_fragments.py` L74-79](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/load_fragments.py#L74-L79).

`piaa-rag` usa un límite fijo: el `max_seq_length` del modelo (128 en `paraphrase-multilingual-MiniLM-L12-v2`), y solo
imprime un aviso cuando un chunk lo pasa. Aquí **el límite es un parámetro**, igual que `max_tokens` en `chunking`:

| Dónde se fija             | Cómo                                                                 | Si no se envía                    |
| ------------------------- | -------------------------------------------------------------------- | --------------------------------- |
| Configuración activa      | `max_tokens` en `PUT`/`PATCH /embeddings/config`                     | `default_tokens` del modelo (128) |
| Corrida de producción     | La de la configuración activa, leída al empezar                      | —                                 |
| Experimento (laboratorio) | `max_tokens` en `POST /embeddings/experiments` (lo pone el pipeline) | `default_tokens` del modelo (128) |
| Búsqueda                  | No se pide: una pregunta es corta                                    | `default_tokens` del modelo (128) |

Cada modelo declara en `MODELS` (A2) dos números: `default_tokens`, lo que lee por defecto (su `max_seq_length`), y
`max_tokens`, el techo que admite su arquitectura (512 posiciones en MiniLM). Se puede pedir cualquier límite entre 1 y
ese techo; fuera de ese rango, 422. Por encima de `default_tokens` el modelo funciona, pero no se entrenó con textos tan
largos: la calidad puede bajar (ver «Decisiones pendientes»).

Lo que no cambia: **un chunk que pase el límite hace fallar su documento sin escribir nada**, nunca se trunca en
silencio. Por eso el `max_tokens` de `chunking` y el de `embeddings` van de la mano. El límite del modelo cuenta dos
tokens especiales que `chunking` no cuenta, así que se fragmenta con 2 menos. **Eso lo asegura el pipeline** (044): en
el laboratorio pone `chunking.max_tokens = límite − 2` y a `embeddings` le pasa el límite; la configuración por defecto
de `chunking` ya es 126, la de `embeddings` 128. A mano, la pareja equivalente es:

```bash
# Chunks de hasta 254 tokens del tokenizador del modelo...
curl -XPATCH localhost:8000/chunking/config -H 'Content-Type: application/json' -d '{
  "tokenizer": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", "max_tokens": 254}'
# ...y vectores con un límite de 256.
curl -XPATCH localhost:8000/embeddings/config -H 'Content-Type: application/json' -d '{"max_tokens": 256}'
```

Cambiar el `max_tokens` de `chunking` cambia su configuración y la siguiente producción vuelve a fragmentar. Cambiar el
de `embeddings` no obliga a recalcular nada: un chunk que cabía se embebe igual con cualquier límite que lo contenga;
solo se reintentan los documentos que fallaron por largos (no tienen huella guardada). El límite usado queda en el
`JSON` (`limite_tokens_embedding`).

---

# Parte A. El módulo `embeddings`

## A1. Dependencias y carpetas

> **Viene de:** [`requirements.txt`](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/requirements.txt)
> (`sentence-transformers`, `neo4j`, `python-dotenv`). Aquí solo hacen falta `transformers` y `torch`.

**Archivo modificado: `pyproject.toml`** (el de la raíz). El extra ya está:

```toml
embed = ["torch>=2.14.1", "transformers>=5.20.2"]
```

`sentence-transformers` no hace falta: el proyecto ya calcula los vectores con `transformers` y `torch`. Falta, en el
mismo archivo (hoy está por error en `src/embeddings/ pyproject.toml`; muévelo y borra ese archivo):

```toml
[tool.uv.build-backend]
module-name = ["ingesta", "data", "parsing", "chunking", "pipeline", "server", "common", "embeddings"]

[tool.ruff.lint.per-file-ignores]
"src/embeddings/adapters/**" = ["TID251"]
"src/embeddings/api/**" = ["TID251"]

[tool.ruff.lint.isort]
known-first-party = ["ingesta", "data", "parsing", "chunking", "pipeline", "server", "embeddings"]
```

**Archivos nuevos:**

```
src/embeddings/
├── __init__.py
├── ruff.toml                    # ya está
├── config/
│   ├── __init__.py              # reexporta settings
│   └── settings.py              # A2
├── models/
│   ├── __init__.py              # reexporta todo
│   ├── concepts.py              # A3
│   ├── requests.py              # A3
│   ├── results.py               # A3
│   ├── stored.py                # A3
│   └── ports.py                 # A3
├── domain/
│   ├── __init__.py
│   ├── fingerprint.py           # A4
│   ├── limits.py                # A4: token_limit (el límite es variable)
│   ├── batches.py               # A4
│   └── runner.py                # A4
├── adapters/
│   ├── __init__.py
│   ├── text_embedder.py         # A5 (lo que hoy está en chunking)
│   ├── local_models.py          # A5
│   ├── session.py               # A7
│   ├── source.py                # A7: fachada de ChunkSource sobre data
│   └── data/                    # A7: clientes y mappers
└── api/
    ├── __init__.py
    ├── app.py                   # A9
    ├── app_info.py
    ├── dependencies.py          # A9
    ├── schemas.py               # A8
    ├── registry.py              # A9
    ├── worker.py                # A9
    ├── processes.py             # A9
    └── routes/
        ├── __init__.py          # ROUTERS
        ├── health.py            # A8
        ├── models.py            # A8: GET /models y POST /vectors
        ├── runs.py              # A8
        └── search.py            # A8
```

**Archivos modificados:**

- El `ruff.toml` de `src/ingesta/`, `src/data/`, `src/parsing/`, `src/chunking/` y `src/pipeline/`: prohibir importar
  `embeddings` (y el de `src/embeddings/`, importar `parsing`).
- `tests/common/test_independent.py`: sumar `"embeddings"` a `MODULES`.
- `src/common/config.py`: `EMBEDDINGS_PATH = "/embeddings"` (lo usan `server`, `embeddings` y `pipeline`).

## A2. Configuración: los modelos en un solo lugar

> **Viene de:** [`llm_models.py` L6-9](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/llm_models.py#L6-L9),
> [`validation/models.py` L6](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/validation/models.py#L6)
> y `src/chunking/config/settings.py:25-31` (`EMBEDDING_MODELS`, `EMBEDDING_CACHE`, `EMBEDDING_BATCH`).

Aquí queda la lista de modelos que el proyecto puede usar, para los fragmentos y para `semantic`. Un modelo nuevo es una
línea más en `MODELS`; ningún otro módulo guarda esa lista.

**Archivo nuevo: `src/embeddings/config/settings.py`.**

```python
"""Default values of the embeddings module: the only list of embedding models of the project."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    dimensions: int
    default_tokens: int  # max_seq_length: the limit when a request doesn't ask for one
    max_tokens: int  # the most a request may ask for: the positions of the model, without its special tokens


MODELS: dict[str, ModelSpec] = {
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2": ModelSpec(
        dimensions=384, default_tokens=128, max_tokens=512
    ),
}
DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"  # of the active config when none is set
MODEL_VERSION = 1  # raise it when the way of embedding changes: every document is embedded again
MODEL_CACHE = ".cache/embeddings"  # the one chunking used: nothing is downloaded again. Relative to the project root
EMBEDDING_BATCH = 32
RUN_TIMEOUT = 300.0  # seconds per request during a run
MAX_WAITING = 100  # runs and experiments waiting in the queue

# What embeddings reads and writes in data. They are data's schema (GET /data/schema), not chunking's: a test checks
# that each one is there (C3).
DOCUMENT_LABEL = "JSON"
SECTION_LABEL = "SECCION"
CHUNK_LABEL = "FRAGMENTOS"
CHUNKED_KEY = "estado_chunking"  # property of the JSON written by chunking (043)
CHUNKED = "fragmentado"  # its value when the document is chunked
EXPERIMENT_LABEL = "EXPERIMENTO"
EXPERIMENT_SECTION_LABEL = "EXP_SECCION"
EXPERIMENT_CHUNK_LABEL = "EXP_CHUNK"
ACTIVE_CONFIG_ID = "embeddings"  # the CONFIG_OFICIAL node of this module
```

`MODEL_CACHE` es la misma carpeta que usaba `chunking`, así que el modelo ya bajado se reutiliza. Ningún límite de
tokens es fijo: `default_tokens` y `max_tokens` solo dicen qué se usa si no se pide nada y hasta dónde se puede pedir
(ver «Requisito previo»). `max_tokens` se declara aquí para no cargar el modelo al responder `GET /models`; un test con
el modelo real (C3) comprueba que no pasa de lo que el modelo admite.

**Archivo nuevo: `src/embeddings/config/__init__.py`.** Sin él, `from embeddings.config import DEFAULT_MODEL` falla
(«símbolo de importación desconocido»): el resto del módulo importa del paquete, nunca de `settings.py`. Reexporta
también las rutas de `common.config`, como hace `chunking`:

```python
"""Values of the embeddings module and the location of the other modules."""

from common.config import DATA_PATH

from .settings import (
    ACTIVE_CONFIG_ID,
    CHUNK_LABEL,
    CHUNKED,
    CHUNKED_KEY,
    DEFAULT_MODEL,
    DOCUMENT_LABEL,
    EMBEDDING_BATCH,
    EXPERIMENT_CHUNK_LABEL,
    EXPERIMENT_LABEL,
    EXPERIMENT_SECTION_LABEL,
    MAX_WAITING,
    MODEL_CACHE,
    MODEL_VERSION,
    MODELS,
    RUN_TIMEOUT,
    SECTION_LABEL,
    ModelSpec,
)

__all__ = [
    "ACTIVE_CONFIG_ID",
    "CHUNKED",
    "CHUNKED_KEY",
    "CHUNK_LABEL",
    "DATA_PATH",
    "DEFAULT_MODEL",
    "DOCUMENT_LABEL",
    "EMBEDDING_BATCH",
    "EXPERIMENT_CHUNK_LABEL",
    "EXPERIMENT_LABEL",
    "EXPERIMENT_SECTION_LABEL",
    "MAX_WAITING",
    "MODELS",
    "MODEL_CACHE",
    "MODEL_VERSION",
    "RUN_TIMEOUT",
    "SECTION_LABEL",
    "ModelSpec",
]
```

Un valor nuevo en `settings.py` se suma también aquí. `src/embeddings/__init__.py` lleva solo un docstring.

## A3. Modelos y puertos

> **Viene de:** [`contract.py` L9-23](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/contract.py#L9-L23)
> (`ChunkIn`) y [`validation/models.py` L56-71](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/validation/models.py#L56-L71)
> (`FragmentoIn`). Los argumentos de [`load_fragments.py` L60-67](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/load_fragments.py#L60-L67)
> pasan a `RunRequest`.

**Archivo nuevo: `src/embeddings/models/concepts.py`.** Reemplaza a `ChunkIn`. Ya no hay `ChunkGraph`: los nombres
del grafo son los de `data` y están en `config` (A2).

```python
"""What lives in memory."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EmbeddableChunk:
    id: str  # the id of its node in data (FRAGMENTOS or EXP_CHUNK), never built here
    text: str  # texto_contextualizado: headings in front of the text (texto_con_contexto in piaa-rag)


@dataclass(frozen=True)
class VectorIndexSpec:
    """A vector index as embeddings asks data for it: data creates it and checks it, but never names it."""

    name: str  # built by domain/indexes.py, never written by hand
    label: str  # the node label whose `embedding` property it indexes
    dimensions: int


@dataclass(frozen=True)
class EmbeddableDocument:
    sha256: str
    chunked: bool  # estado_chunking is fragmentado: only those are embedded
    fingerprint: str | None  # huella_embedding: what it was embedded from, if it was


@dataclass(frozen=True)
class EmbeddingConfig:
    """The active configuration (CONFIG_OFICIAL of this module), or one an experiment tries."""

    model: str
    max_tokens: int
    origin: str = "defecto"  # defecto | experimento | manual
    experiment: str | None = None
```

**Archivo nuevo: `src/embeddings/models/requests.py`.** `--force` de `piaa-rag` es `force`; `--replace` no hace falta;
`--with-clip` queda fuera. Ni `limit` ni «todos»: el pipeline dice qué.

```python
"""What is asked for."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RunRequest:
    """Production: these chunked documents, with the active configuration (read when the run starts)."""

    sha256s: list[str]  # never empty: whoever calls (the pipeline, or someone by hand) chooses
    simulate: bool = False
    force: bool = False  # embed again even if nothing changed


@dataclass(frozen=True)
class ExperimentRequest:
    """Laboratory: the chunks of a chunking experiment, with a model and a limit to try."""

    chunking_experiment: str  # id of the EXPERIMENTO of chunking
    model: str
    max_tokens: int | None = None  # None: the model's default_tokens
    name: str = ""
    simulate: bool = False
```

**Archivo nuevo: `src/embeddings/models/results.py`.**

```python
"""What a run or an experiment reports."""

from dataclasses import dataclass, field
from enum import StrEnum

from .concepts import EmbeddingConfig


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"


@dataclass(frozen=True)
class RunProgress:
    embedded: int = 0
    chunks: int = 0
    unchanged: int = 0
    skipped: int = 0  # not chunked, partial or in error
    missing: int = 0  # a sha256 asked for with no JSON in data
    errors: int = 0


@dataclass(frozen=True)
class DocumentFailure:
    sha256: str
    error: str


@dataclass(frozen=True)
class EmbeddingRun:
    id: str
    status: RunStatus
    requested: str
    config: EmbeddingConfig  # what it used: the active one when it started, or the experiment's
    finished: str | None = None
    progress: RunProgress = field(default_factory=RunProgress)
    failures: list[DocumentFailure] = field(default_factory=list)
    embedded: list[str] = field(default_factory=list)  # sha256s with vectors: what the pipeline reads
    error: str | None = None


@dataclass(frozen=True)
class SearchHit:
    id: str
    score: float
    text: str
    headings: list[str]
    pages: list[int]
    sha256: str
    origin: str
    code: str | None
```

Un experimento responde con la misma forma (`EmbeddingRun`, con su
`id` de experimento): no hace falta otra clase. Falta `EmbeddingRun.simulated(progress)`, que arma la respuesta de una
simulación (A9). `TextVectors` ya no existe: era la respuesta de `POST /vectors`, que se quita (nadie la llama).

**Archivo nuevo: `src/embeddings/models/stored.py`.** Reemplaza a `FragmentoIn`. Los nombres son datos guardados: van
en español.

```python
"""What is stored in the graph. A key added here is written by domain/batches.py."""

from typing import TypedDict

# Only this module's own properties, the ones it writes (with merge) on the nodes chunking created. The labels and
# chunking's status are data's schema (config).


class FragmentVector(TypedDict):
    embedding: list[float]
    modelo_embedding: str
    version_embedding: int


class DocumentVectors(TypedDict):
    huella_embedding: str
    embebido_en: str
    modelo_embedding: str
    limite_tokens_embedding: int  # the limit the run used


class ConfigProperties(TypedDict):
    modulo: str  # "embeddings"
    modelo: str
    max_tokens: int
    origen: str
    experimento: str
    modificado_en: str
```

**Archivo nuevo: `src/embeddings/models/ports.py`.** El dominio no ve HTTP ni modelos: ve estas interfaces, y con ellas
se prueba con objetos falsos. Todas se implementan sobre `data`.

```python
"""What the domain asks of the outside, and the errors of each side."""

from typing import Protocol

from .concepts import EmbeddableChunk, EmbeddableDocument, EmbeddingConfig, VectorIndexSpec
from .results import SearchHit
from .stored import DocumentVectors, FragmentVector


class UpstreamDown(Exception):
    """data doesn't answer, or the model can't be loaded: it stops the run, nothing is written."""


class DocumentError(Exception):
    """Only this document fails: the others go on."""


class InvalidLimit(Exception):
    """A token limit the model doesn't admit: 422, nothing runs."""


class ChunkSource(Protocol):
    """The chunks as chunking left them in data."""

    def document(self, sha256: str) -> EmbeddableDocument | None: ...

    def chunks(self, sha256: str) -> list[EmbeddableChunk]:
        """FRAGMENTOS under JSON → SECCION, in order."""
        ...

    def experiment_chunks(self, experiment: str) -> dict[str, list[EmbeddableChunk]]:
        """EXP_CHUNK under EXPERIMENTO → EXP_SECCION, by sha256; empty if the experiment doesn't exist."""
        ...


class VectorSink(Protocol):
    def ensure_index(self, index: VectorIndexSpec) -> None:
        """Creates it if missing; UpstreamDown if one with that name exists with another definition."""
        ...

    def save(self, label: str, sha256: str | None, document: DocumentVectors | None,
             chunks: dict[str, FragmentVector]) -> None:
        """All of a document or nothing: the chunks of `label` and, in production, its JSON."""
        ...


class ConfigStore(Protocol):
    def active(self) -> EmbeddingConfig | None: ...

    def set(self, config: EmbeddingConfig) -> None: ...

    def clear(self) -> None: ...


class VectorIndexSearch(Protocol):
    def search(self, index: str, vector: list[float], k: int) -> list[SearchHit]:
        """Nothing if the index doesn't exist yet (nothing was embedded)."""
        ...


class Embedder(Protocol):
    """Any model of config.MODELS, by name."""

    def embed(self, model: str, texts: list[str], max_tokens: int) -> list[list[float]]:
        """What is longer than `max_tokens` is cut: whoever calls checks the lengths first if that matters."""
        ...

    def tokens(self, model: str, text: str) -> int: ...
```

**Archivo nuevo: `src/embeddings/models/__init__.py`.** Igual que en `config/`: el dominio, los adaptadores y la API
importan de `embeddings.models`, así que cada clase nueva se suma aquí (`ChunkSource`, `ConfigStore`, `DocumentError`,
`DocumentFailure`, `DocumentVectors`, `EmbeddableChunk`, `EmbeddableDocument`, `Embedder`, `EmbeddingConfig`,
`EmbeddingRun`, `ExperimentRequest`, `FragmentVector`, `ConfigProperties`, `InvalidLimit`, `RunProgress`, `RunRequest`,
`RunStatus`, `SearchHit`, `UpstreamDown`, `VectorIndexSearch`, `VectorIndexSpec`, `VectorSink`), con su `__all__`.

**Lo que ya está escrito en `src/embeddings/models/`** (de la versión anterior de esta guía) se ajusta a lo de arriba:
se quitan `ChunkGraph`, `TextVectors`, `limit` y la lista vacía de `RunRequest`; `ChunkSource` deja de tener `graph` y
`documents`; `port.py` pasa a llamarse `ports.py`.

## A4. El dominio: reglas sin I/O

> **Viene de:** [`load_fragments.py` L54-56](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/load_fragments.py#L54-L56)
> (`fingerprint`), [L69-121](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/load_fragments.py#L69-L121)
> (el bucle de `main`) y [L32-39](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/load_fragments.py#L32-L39)
> (`Q_WRITE`).

**Archivo nuevo: `src/embeddings/domain/fingerprint.py`.** En `piaa-rag` hay una huella por chunk; aquí es por
documento: se escribe en una sola transacción y evita leer la huella de cada chunk.

```python
"""What a document's vectors depend on: if any of it changes, they are calculated again."""

import hashlib

from embeddings.config import MODEL_VERSION
from embeddings.models import EmbeddableChunk


def document_fingerprint(model: str, chunks: list[EmbeddableChunk]) -> str:
    base = "\n".join([f"{model}|{MODEL_VERSION}", *(f"{c.id}|{c.text}" for c in chunks)])
    return "sha256:" + hashlib.sha256(base.encode("utf-8")).hexdigest()
```

**Archivo nuevo: `src/embeddings/domain/limits.py`.** La única regla del límite, para la configuración, las corridas,
los experimentos y la búsqueda:

```python
"""The token limit of a request: asked or the model's default, never past what the model admits."""

from embeddings.config import MODELS
from embeddings.models import InvalidLimit


def token_limit(model: str, asked: int | None) -> int:
    spec = MODELS[model]
    if asked is None:
        return spec.default_tokens
    if not 1 <= asked <= spec.max_tokens:
        raise InvalidLimit(f"max_tokens must be between 1 and {spec.max_tokens} for {model}")
    return asked
```

**Archivo nuevo: `src/embeddings/domain/indexes.py`.** El nombre del índice vectorial no se escribe en ningún lado: se
arma con lo que lo identifica. Reemplaza el `fragmento_emb_minilm_v1` que `piaa-rag` escribe a mano en
[`001_schema.cypher` L67](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/scripts/001_schema.cypher#L67)
y en [`search.py` L20](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/search.py#L20).

```python
"""The vector index of each model: its name says what it holds, so a new model or dimension is a new index by itself."""

import re

from embeddings.config import MODELS
from embeddings.models import VectorIndexSpec


def index_name(label: str, model: str, dimensions: int) -> str:
    """vec_<label>_<model without its owner>_<dimensions>, lowercase and only [a-z0-9_]:
    vec_fragmentos_paraphrase_multilingual_minilm_l12_v2_384."""
    short = model.rsplit("/", 1)[-1]
    parts = [re.sub(r"[^a-z0-9]+", "_", part.lower()).strip("_") for part in (label, short)]
    return "_".join(["vec", *parts, str(dimensions)])


def vector_index(label: str, model: str) -> VectorIndexSpec:
    """The index of `model` over the nodes of `label` (CHUNK_LABEL or EXPERIMENT_CHUNK_LABEL, data's names)."""
    dimensions = MODELS[model].dimensions
    return VectorIndexSpec(index_name(label, model, dimensions), label, dimensions)
```

Por qué así:

- **Dice qué tiene:** de qué nodos (`fragmentos`), con qué modelo y de cuántas dimensiones.
- **Cambia cuando debe:** otro modelo u otra dimensión dan otro índice (un índice de Neo4j nunca cambia de dimensión).
  `MODEL_VERSION` no entra: subirla recalcula los vectores, pero caben en el mismo índice.
- **Es estable:** el mismo modelo da siempre el mismo nombre, en cada corrida y en cada búsqueda.

**Archivo nuevo: `src/embeddings/domain/runner.py`.** Es el bucle de `main()` sin base de datos, con los errores
separados: si falla la máquina se corta la corrida; si falla el documento, se siguen los demás. Recibe la
configuración ya resuelta (la activa, leída al empezar) y solo los `sha256` que le pasaron.

```python
"""Runner: embeds the given chunked documents that changed. A bad document never stops it; only the outside does."""

from collections.abc import Callable
from dataclasses import replace

from common.clock import now
from embeddings.config import CHUNK_LABEL, MODEL_VERSION
from embeddings.models import (
    ChunkSource,
    DocumentError,
    DocumentFailure,
    DocumentVectors,
    Embedder,
    EmbeddingConfig,
    FragmentVector,
    RunProgress,
    RunRequest,
    VectorSink,
)

from .fingerprint import document_fingerprint
from .indexes import vector_index


class Runner:
    @staticmethod
    def run(
        source: ChunkSource,
        sink: VectorSink,
        embedder: Embedder,
        config: EmbeddingConfig,
        request: RunRequest,
        on_progress: Callable[[RunProgress], None],
        on_failure: Callable[[DocumentFailure], None],
        on_embedded: Callable[[str], None],
    ) -> RunProgress:
        """UpstreamDown goes through: whoever runs it marks the run as failed."""
        model, limit = config.model, config.max_tokens
        if not request.simulate:
            sink.ensure_index(vector_index(CHUNK_LABEL, model))  # idempotent: before any vector
        progress = RunProgress()
        for sha256 in dict.fromkeys(request.sha256s):
            document = source.document(sha256)
            if document is None:  # asked for, but not in data: counted, like chunking's sin_parseo
                on_failure(DocumentFailure(sha256, "no JSON in data"))
                progress = replace(progress, missing=progress.missing + 1)
                continue
            if not document.chunked:  # not chunked, partial or in error: waits
                progress = replace(progress, skipped=progress.skipped + 1)
                continue
            try:
                chunks = source.chunks(sha256)
                fingerprint = document_fingerprint(model, chunks)
                if fingerprint == document.fingerprint and not request.force:
                    progress = replace(progress, unchanged=progress.unchanged + 1)
                    continue
                long = [c.id for c in chunks if embedder.tokens(model, c.text) > limit]
                if long:
                    raise DocumentError(f"{len(long)} chunks go over {limit} tokens, e.g. {long[0]}")
                if not request.simulate:
                    vectors = embedder.embed(model, [c.text for c in chunks], limit)
                    sink.save(
                        CHUNK_LABEL,
                        sha256,
                        DocumentVectors(
                            huella_embedding=fingerprint, embebido_en=now(), modelo_embedding=model,
                            limite_tokens_embedding=limit,
                        ),
                        {
                            c.id: FragmentVector(embedding=v, modelo_embedding=model, version_embedding=MODEL_VERSION)
                            for c, v in zip(chunks, vectors, strict=True)
                        },
                    )
                    on_embedded(sha256)
                progress = replace(progress, embedded=progress.embedded + 1, chunks=progress.chunks + len(chunks))
            except DocumentError as error:
                on_failure(DocumentFailure(sha256, str(error)))
                progress = replace(progress, errors=progress.errors + 1)
            on_progress(progress)
        return progress
```

**Archivo nuevo: `src/embeddings/domain/experiments.py`.** El laboratorio: los `EXP_CHUNK` de un experimento de
chunking, con el modelo y el límite que se prueban. Mismo bucle por documento (`source.experiment_chunks`), índice
sobre `EXPERIMENT_CHUNK_LABEL` y `sink.save(EXPERIMENT_CHUNK_LABEL, None, None, vectors)`: no toca el `JSON` oficial
ni compara huellas (cada experimento se calcula entero). Un experimento de chunking que no existe → 404 al crearlo.
`ExperimentRunner.apply(store, experiment)` copia su `EmbeddingConfig` a la activa (`origin="experimento"`).

**Archivo nuevo: `src/embeddings/domain/active_config.py`.** `resolve(store) -> EmbeddingConfig`: la guardada si su
modelo está en `MODELS` y su límite cabe (`token_limit`); si no, `DEFAULT_MODEL` con su `default_tokens`. Lo usan la
corrida (al empezar), la búsqueda y `GET /config`.

**Archivo nuevo: `src/embeddings/domain/__init__.py`.** Reexporta las reglas; súmalas a medida que creas cada archivo
(importar uno que aún no existe rompe el paquete):

```python
"""Rules of the embeddings module, without I/O; everything is imported from embeddings.domain."""

from .active_config import resolve
from .batches import vectors_batch
from .experiments import ExperimentRunner
from .fingerprint import document_fingerprint
from .indexes import index_name, vector_index
from .limits import token_limit
from .runner import Runner

__all__ = [
    "ExperimentRunner",
    "Runner",
    "document_fingerprint",
    "index_name",
    "resolve",
    "token_limit",
    "vector_index",
    "vectors_batch",
]
```

**Función intermedia: `src/embeddings/domain/batches.py`.** Reemplaza `Q_WRITE`: arma el cuerpo de `POST /data/batch`.

```python
"""A document's vectors as a batch of data: `merge` keeps the text and everything else of each node."""

from collections.abc import Mapping

from embeddings.config import DOCUMENT_LABEL
from embeddings.models import DocumentVectors, FragmentVector


def vectors_batch(
    label: str, sha256: str | None, document: DocumentVectors | None, chunks: Mapping[str, FragmentVector]
) -> dict[str, object]:
    """The chunks of `label` (FRAGMENTOS or EXP_CHUNK) and, in production, its JSON (its id is the sha256)."""
    nodes: list[dict[str, object]] = [
        {"label": label, "id": id, "properties": properties, "mode": "merge"} for id, properties in chunks.items()
    ]
    if sha256 is not None and document is not None:
        nodes.append({"label": DOCUMENT_LABEL, "id": sha256, "properties": document, "mode": "merge"})
    return {"nodes": nodes, "relationships": []}
```

Un solo lote por documento hace que todo se escriba o nada. `piaa-rag` escribe de a 500
([L117-120](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/load_fragments.py#L117-L120))
y, si falla a mitad, deja el documento incompleto. Cada vector ocupa unos 8 KB en JSON: con el límite de 32 MiB de
`--max-body-bytes` caben unos 4 000 chunks por documento.

## A5. El modelo de vectores: el único lugar que lo carga

> **Viene de:** `src/chunking/adapters/strategies/embeddings.py` (`_Embedder`, completo),
> `src/chunking/adapters/strategies/tokens.py:11-16` (`pretrained`), `src/chunking/adapters/strategies/tools.py:35-40`
> (`Models.embed`: uno por nombre, con lock) y, en `piaa-rag`,
> [`llm_models.py` L12-34](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/llm_models.py#L12-L34)
> (`load_model` con `lru_cache`, `embed`, `find_long_chunks`).

El código de `chunking` se **copia** aquí: la feature 043 lo borra de `chunking` (Parte B). Va en `adapters/`, que es donde se
admite `Any`; así ya no hace falta un `common/local_models.py`.

**Archivo nuevo: `src/embeddings/adapters/text_embedder.py`.** Es `_Embedder` con dos cambios: `max_length` **por
llamada** (cada petición elige su límite; el modelo se carga una sola vez para todas) y `tokens` (lo que hacía
`find_long_chunks`).

```python
"""A local sentence embedding model: mean pooling of the token vectors, normalized (what sentence-transformers does
for these models), with transformers and torch. They come with the `embed` extra; loaded when it is built."""

from importlib import import_module
from typing import Any

type Loaded = Any  # an object of transformers or torch (untyped from here)


def pretrained(kind: Loaded, name: str, cache: str) -> Loaded:
    """From `cache` without network; downloaded there the first time."""
    try:
        return kind.from_pretrained(name, cache_dir=cache, local_files_only=True)
    except OSError:
        return kind.from_pretrained(name, cache_dir=cache)


class TextEmbedder:
    def __init__(self, name: str, cache: str, batch: int) -> None:
        transformers = import_module("transformers")
        self._torch = import_module("torch")
        self._batch = batch
        self._tokenizer = pretrained(transformers.AutoTokenizer, name, cache)
        self._model = pretrained(transformers.AutoModel, name, cache)
        self._model.eval()

    def embed(self, texts: list[str], max_length: int) -> list[list[float]]:
        torch = self._torch
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch):
            encoded = self._tokenizer(
                texts[start : start + self._batch],
                padding=True,
                truncation=True,
                max_length=max_length,
                return_tensors="pt",
            )
            with torch.no_grad():
                hidden = self._model(**encoded).last_hidden_state
            mask = encoded["attention_mask"].unsqueeze(-1).float()
            mean = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
            vectors += torch.nn.functional.normalize(mean, dim=1).tolist()
        return vectors

    def tokens(self, text: str) -> int:
        """With the model's special tokens, as it reads them."""
        return len(self._tokenizer(text, add_special_tokens=True)["input_ids"])
```

**Archivo nuevo: `src/embeddings/adapters/local_models.py`.** Implementa `Embedder`: un `TextEmbedder` por modelo,
cargado la primera vez (el `lru_cache` de `piaa-rag`, seguro entre hilos). Cualquier fallo al cargarlo es de la
máquina, no del documento.

```python
"""Embedder with the local models of config.MODELS, each loaded once."""

import threading
from pathlib import Path

from embeddings.config import EMBEDDING_BATCH, MODEL_CACHE
from embeddings.models import UpstreamDown

from .text_embedder import TextEmbedder

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


class LocalModels:
    def __init__(self, cache: str | None = None) -> None:
        self._cache = cache or str(_PROJECT_ROOT / MODEL_CACHE)
        self._lock = threading.Lock()
        self._loaded: dict[str, TextEmbedder] = {}

    def _model(self, name: str) -> TextEmbedder:
        with self._lock:
            if name not in self._loaded:
                try:
                    self._loaded[name] = TextEmbedder(name, self._cache, EMBEDDING_BATCH)
                except (ImportError, OSError) as error:
                    raise UpstreamDown(f"the model {name} can't be loaded: {error}") from error
            return self._loaded[name]

    def embed(self, model: str, texts: list[str], max_tokens: int) -> list[list[float]]:
        return self._model(model).embed(texts, max_tokens)

    def tokens(self, model: str, text: str) -> int:
        return self._model(model).tokens(text)
```

`pathlib` se admite aquí porque `src/embeddings/adapters/**` ignora `TID251` (A1), igual que
`src/chunking/adapters/strategies/tools.py`, que resuelve su caché de la misma forma.

## A6. Cambiar `data`: crear índices vectoriales y buscar

> **Viene de:** [`001_schema.cypher` L66-69](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/scripts/001_schema.cypher#L66-L69)
> (el índice) y [`search.py` L19-29](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/search.py#L19-L29)
> (`Q_FRAGMENTS`).

Solo `data` toca Neo4j, pero **`data` no sabe qué índices hacen falta**: eso depende del modelo, y los modelos están en
`embeddings`. Así que `data` pone las reglas (qué nombre es válido, sobre qué etiquetas, en qué propiedad) y
`embeddings` le pide el índice que necesita (`vector_index`, A4). Ningún nombre de índice ni dimensión queda escrito en
`data`.

No hace falta una etiqueta nueva: los vectores son la propiedad `embedding` de `FRAGMENTOS` (producción) y de
`EXP_CHUNK` (laboratorio), cada una con su índice. Frente a `Q_FRAGMENTS`: no se filtra por `obsoleto` ni por
`estrategia_chunking` (no existen aquí) y sí por `j.estado_chunking` (la propiedad que escribe `chunking`, 043). El
origen y el código salen del `RAW` del documento (`JSON -[:VIENE_DE]-> RAW`, 042): la metadata del archivo ya no se
copia al `JSON`.

**Archivo nuevo: `src/data/schema/vector_rules.py`.** Las reglas, como `batch_rules.py`:

```python
"""What a vector index may be. The names come from whoever asks (embeddings); the rules are data's."""

import re

from data.models import Label

VECTOR_PROPERTY = "embedding"  # where every vector lives, on any label
MAX_DIMENSIONS = 4096  # what Neo4j admits
_NAME = re.compile(r"^vec_[a-z0-9_]{1,120}$")


def index_problems(name: str, label: Label, dimensions: int) -> list[str]:
    problems: list[str] = []
    if not _NAME.fullmatch(name):
        problems.append("the name must be vec_ followed by lowercase letters, digits or _")
    if not 1 <= dimensions <= MAX_DIMENSIONS:
        problems.append(f"dimensions must be between 1 and {MAX_DIMENSIONS}")
    if label not in (Label.FRAGMENTOS, Label.EXP_CHUNK):
        problems.append("only chunks have vectors: FRAGMENTOS or EXP_CHUNK")
    return problems
```

`label` es `Label`: FastAPI rechaza (422) una etiqueta que no esté en el enum, así que solo se concatenan valores del
enum, como en el resto de `data`.

**Archivo nuevo: `src/data/repository/vector_repository.py`.**

```python
"""Vector indexes and the search over them. The name and the vector go as parameters; only the label (an enum) and
the property (a constant) are concatenated."""

from typing import LiteralString

from data.models import GraphAdapter, GraphRow, Label
from data.schema.vector_rules import VECTOR_PROPERTY

from .cypher import integer, name

_PROPERTY: LiteralString = "embedding"
assert _PROPERTY == VECTOR_PROPERTY

_FIND: LiteralString = """
SHOW VECTOR INDEXES YIELD name, labelsOrTypes, properties, options
WHERE name = $name
RETURN labelsOrTypes[0] AS label, properties[0] AS property, options.indexConfig['vector.dimensions'] AS dimensions
"""

_SEARCH: LiteralString = """
CALL db.index.vector.queryNodes($index, $candidates, $vector) YIELD node AS f, score
MATCH (j:JSON)-[:TIENE_SECCION]->(s:SECCION)-[:TIENE_FRAGMENTO]->(f)
WHERE j.estado_chunking = 'fragmentado'
OPTIONAL MATCH (j)-[:VIENE_DE]->(r:RAW)
RETURN f.id AS id, f.texto AS text, f.encabezados AS headings, f.paginas AS pages,
       j.id AS sha256, r.origen AS origin, r.codigo AS code, score
ORDER BY score DESC
LIMIT $k
"""


class VectorIndexConflict(Exception):
    """An index with that name exists with another definition: 409."""


class VectorRepository:
    def __init__(self, graph: GraphAdapter) -> None:
        self._graph = graph

    def find(self, index: str) -> GraphRow | None:
        rows = self._graph.read(_FIND, {"name": index})
        return rows[0] if rows else None

    def ensure(self, index: str, label: Label, dimensions: int) -> GraphRow:
        """Creates it if missing; an existing one must be the same (IF NOT EXISTS alone would hide the difference)."""
        found = self.find(index)
        if found is None:
            self._graph.write(
                "CREATE VECTOR INDEX $name IF NOT EXISTS FOR (n:" + name(label) + ") ON n." + _PROPERTY + " "
                "OPTIONS { indexConfig: { `vector.dimensions`: $dimensions, `vector.similarity_function`: 'cosine' } }",
                {"name": index, "dimensions": dimensions},
            )
            found = self.find(index)
        assert found is not None
        if (found["label"], found["property"], integer(found["dimensions"])) != (label.value, _PROPERTY, dimensions):
            where = f"{found['label']}.{found['property']}, {found['dimensions']} dimensions"
            raise VectorIndexConflict(f"{index} already exists on {where}")
        return found

    def search(self, index: str, vector: list[float], k: int) -> list[GraphRow]:
        # The filter runs after the index: more candidates are asked for than are returned (as piaa-rag does).
        return self._graph.read(_SEARCH, {"index": index, "vector": vector, "k": k, "candidates": k * 10})
```

Antes de dar esto por bueno, **comprueba en el Neo4j temporal que `CREATE VECTOR INDEX $name` acepta el nombre como
parámetro** (lo probado hasta ahora fue `$dimensions`). Si no lo acepta, el nombre tiene que concatenarse: valídalo con
`_NAME` y conviértelo a `LiteralString` en una sola función de `cypher.py`, como `name()` hace con los enums.

**Archivo nuevo: `src/data/api/routes/vectors.py`.**

```python
"""Vector indexes (PUT /vectors/indexes/{name}, GET /vectors/indexes/{name}) and the search (POST /vectors/search)."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from data.api.dependencies import Graph
from data.models import GraphRow, Label
from data.repository.vector_repository import VectorIndexConflict, VectorRepository
from data.schema.vector_rules import index_problems

router = APIRouter(prefix="/vectors", tags=["vectors"])


@dataclass(frozen=True)
class VectorIndexBody:
    label: Label
    dimensions: int


@dataclass(frozen=True)
class VectorSearch:
    index: str
    vector: list[float]


def _repository(graph: Graph) -> VectorRepository:
    return VectorRepository(graph)


Repository = Annotated[VectorRepository, Depends(_repository)]


@router.put("/indexes/{index}")
def ensure_index(repository: Repository, index: str, body: VectorIndexBody) -> GraphRow:
    problems = index_problems(index, body.label, body.dimensions)
    if problems:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "; ".join(problems))
    try:
        return repository.ensure(index, body.label, body.dimensions)
    except VectorIndexConflict as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error


@router.get("/indexes/{index}")
def read_index(repository: Repository, index: str) -> GraphRow:
    found = repository.find(index)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"there is no vector index {index!r}")
    return found


@router.post("/search")
def search(repository: Repository, body: VectorSearch, k: Annotated[int, Query(ge=1, le=100)] = 5) -> list[GraphRow]:
    found = repository.find(body.index)
    if found is None:  # nothing embedded yet
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"there is no vector index {body.index!r}")
    if found["label"] != Label.FRAGMENTOS.value:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "this search reads fragments: a FRAGMENTOS index")
    if len(body.vector) != found["dimensions"]:  # Neo4j would refuse it, and data answers any GraphError as a 503
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"the index has {found['dimensions']} dimensions")
    return repository.search(body.index, body.vector, k)
```

La búsqueda recorre `JSON → SECCION → FRAGMENTOS`, así que solo sirve para índices de `FRAGMENTOS`. Vectores de otra
etiqueta (imágenes, por ejemplo) necesitarían su propia consulta.

**Archivos modificados:**

- `src/data/api/routes/__init__.py`: sumar `vectors.router` a `ROUTERS`.
- `src/server/console/texts.py`: nombres en español del recurso y de sus rutas.
- `tests/server/console/test_catalog.py`: sumar `"vectors"` a los recursos de `data` que lista
  `test_every_operation_is_in_one_resource_with_a_spanish_name`.

`server/graph.py` **no cambia**: el índice no se crea al arrancar, lo pide `embeddings` al empezar cada corrida
(`Runner`, A4). Antes de la primera corrida no hay índice, y `POST /embeddings/search` responde una lista vacía.

## A6b. (Se quitó) `chunking` ya no publica sus nombres

La versión anterior de esta guía agregaba `GET /chunking/graph` y un `id` en `GET /chunking/documents/{sha256}/chunks`
para que `embeddings` leyera los chunks a través de `chunking`. Con la regla de los módulos (042) eso no va:
`embeddings` lee de `data`, y los nombres (`JSON`, `SECCION`, `FRAGMENTOS`, `EXP_SECCION`, `EXP_CHUNK`,
`estado_chunking`, `fragmentado`) son del esquema de `data`, que es el contrato de todos. Están en `config` (A2) y un
test los compara con `GET /data/schema` (C3). `GET /chunking/documents*` ya no existe (043). No se toca `chunking`.

## A7. Los adaptadores HTTP

> **Viene de:** [`contract.py` L26-49](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/contract.py#L26-L49)
> (leer los chunks), [`load_fragments.py` L26-30 y L88-93](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/load_fragments.py#L88-L93)
> (huellas guardadas) y [L82-86](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/load_fragments.py#L82-L86)
> (la conexión, que aquí es un `httpx.Client` hacia el mismo servidor). Forma: `src/chunking/adapters/data/`.

Todos hablan con `data`, sobre `common.http.BaseHttpClient`:

| Archivo                             | Implementa                                                    | Llama a                                                                                                                       |
| ----------------------------------- | ------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `adapters/data/documents_client.py` | `ChunkSource.document`                                        | `GET /data/nodes/JSON/{sha256}`                                                                                               |
| `adapters/data/chunks_client.py`    | `ChunkSource.chunks`, `.experiment_chunks`                    | `GET /data/nodes/{label}/{id}/relationships` para bajar `JSON → SECCION → FRAGMENTOS` y `EXPERIMENTO → EXP_SECCION → EXP_CHUNK` |
| `adapters/data/vector_client.py`    | `VectorSink`, `VectorIndexSearch`                             | `PUT /data/vectors/indexes/{name}`, `POST /data/batch`, `POST /data/vectors/search` (404 → lista vacía; 409 → `UpstreamDown`) |
| `adapters/data/config_client.py`    | `ConfigStore`                                                 | `GET`/`PUT`/`DELETE /data/nodes/CONFIG_OFICIAL/embeddings`                                                                    |
| `adapters/data/mappers.py`          | —                                                             | Nodo `JSON` → `EmbeddableDocument`; nodo de chunk → `EmbeddableChunk`; fila → `SearchHit`; nodo → `EmbeddingConfig`           |
| `adapters/source.py`                | Fachada de `ChunkSource` que compone los dos primeros clientes | —                                                                                                                             |
| `adapters/session.py`               | `HttpSession`: un `httpx.Client` por corrida                  | Como `src/chunking/adapters/session.py`                                                                                       |

El id de cada chunk es el de su nodo en `data`; el mapper no lo arma:

```python
"""data's nodes as embeddings' values."""

from collections.abc import Mapping

from common.http import Json
from embeddings.config import CHUNKED, CHUNKED_KEY
from embeddings.models import EmbeddableChunk, EmbeddableDocument


def chunk(raw: Mapping[str, Json]) -> EmbeddableChunk:
    properties = raw["properties"]
    assert isinstance(properties, Mapping)
    return EmbeddableChunk(str(raw["id"]), str(properties.get("texto_contextualizado") or properties["texto"]))


def document(raw: Mapping[str, Json]) -> EmbeddableDocument:
    properties = raw["properties"]
    assert isinstance(properties, Mapping)
    fingerprint = properties.get("huella_embedding")
    return EmbeddableDocument(
        str(raw["id"]), properties.get(CHUNKED_KEY) == CHUNKED, str(fingerprint) if fingerprint else None
    )
```

(`EXP_CHUNK` no guarda `texto_contextualizado` hoy; si la 043 no lo agrega, se usa `texto`. Los chunks se ordenan por
`orden` de su sección y su `indice`.)

Política de errores de todos los clientes:

```python
ERRORS = ErrorPolicy("data", UpstreamDown, DocumentError)  # red, timeout o 5xx corta la corrida; otro 4xx, el documento
```

**Muchas llamadas para bajar los chunks.** `data` no tiene una lectura en profundidad: un documento son 1 + secciones
llamadas. Para el corpus de hoy alcanza; si pesa, la mejora va en `data` (una ruta que siga las relaciones de
composición desde un nodo), no en `chunking`. `GET /data/nodes/JSON/{sha256}` además devuelve el `documento` entero del
parseo (042): el mapper solo lee lo que necesita, pero viaja igual.

## A8. Los endpoints

> **Desde la 048:** `POST /embeddings/search` ya no existe (la búsqueda es de `consultas`) y `POST /embeddings/vectors`
> volvió como texto → vector. Ver «Cambios por la feature 048» al inicio.

> **Viene de:** [`search.py` L38-43 y L52-68](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/search.py#L38-L68)
> (la búsqueda, que era una CLI) y [`load_fragments.py` L59-67](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/load_fragments.py#L59-L67)
> (la corrida, también CLI). La configuración activa y los experimentos siguen la forma de `chunking` (043).

Como en los demás módulos de trabajo: **acciones, estado de sus procesos y configuración**. Lo guardado (los vectores) se
lee en `data`; no hay rutas que lean documentos o chunks.

| Método y ruta                                                       | Qué hace                                                                                 | Respuestas                                                                                                 |
| ------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `GET /embeddings/health`                                            | Si hay modelo y si data responde                                                         | 200 siempre                                                                                                |
| `GET /embeddings/models`                                            | Los modelos de `MODELS`, con dimensiones, límite por defecto y máximo (el pipeline lo usa) | 200                                                                                                        |
| `GET /embeddings/config`                                            | La configuración activa (modelo, `max_tokens`, origen) o la de por defecto               | 200                                                                                                        |
| `PUT`/`PATCH /embeddings/config`, `DELETE /embeddings/config`       | Editarla a mano; volver a la de por defecto                                              | 200; 422 si el modelo no está o el límite no cabe                                                          |
| `POST /embeddings/runs`                                             | `{sha256s, force, simulate}`: embebe esos documentos con la configuración activa         | 202 en cola; 200 con `simulate`; 422 si `sha256s` está vacía; 409 si la fila está llena; 503 sin modelo con `simulate` |
| `GET /embeddings/runs`, `GET /embeddings/runs/{id}`                 | Estado, progreso, fallos y los `sha256` embebidos                                        | 200; 404                                                                                                   |
| `POST /embeddings/experiments`                                      | `{name, chunking_experiment, model, max_tokens, simulate}`: embebe sus `EXP_CHUNK`        | 202 en cola; 200 con `simulate`; 404 si el experimento de chunking no existe; 422 si el modelo o el límite no caben |
| `GET /embeddings/experiments`, `GET`/`DELETE /embeddings/experiments/{id}` | Estado y resultados; borrar (sus vectores en los `EXP_CHUNK`)                     | 200; 404                                                                                                   |
| `POST /embeddings/experiments/{id}/apply`                           | Copia su modelo y límite a la configuración activa; no procesa nada                      | 200; 404; 409 si no terminó                                                                                |
| `POST /embeddings/search` (048: **se quitó**, ver `POST /consultas/search`) | Los fragmentos oficiales más parecidos a una pregunta, con el modelo activo      | 200; 503 si no hay modelo o `data` no responde                                                             |
| `GET /embeddings/processes`, `WS /embeddings/processes/ws`          | Tablero de procesos (A9)                                                                 | 200                                                                                                        |

`POST /embeddings/vectors` **se quita**: solo lo usaba la estrategia `semantic` de `chunking`, que la 043 borra. (048:
volvió, para que `consultas` vectorice sus preguntas.)

**Archivo nuevo: `src/embeddings/api/schemas.py`.** Las claves desconocidas dan 422, como en el resto del proyecto.

```python
"""Bodies of the requests and answers."""

from dataclasses import dataclass
from typing import Annotated

from pydantic import ConfigDict, Field

STRICT = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class NewRun:
    __pydantic_config__ = STRICT

    sha256s: Annotated[list[str], Field(min_length=1)]  # the pipeline (or someone by hand) chooses
    simulate: bool = False
    force: bool = False


@dataclass(frozen=True)
class NewExperiment:
    __pydantic_config__ = STRICT

    chunking_experiment: Annotated[str, Field(min_length=1)]
    model: str
    max_tokens: Annotated[int, Field(ge=1)] | None = None  # the ceiling depends on the model: domain/limits.py
    name: str = ""
    simulate: bool = False


@dataclass(frozen=True)
class ConfigBody:
    __pydantic_config__ = STRICT

    model: str
    max_tokens: Annotated[int, Field(ge=1)] | None = None


@dataclass(frozen=True)
class ConfigPatch:
    __pydantic_config__ = STRICT

    model: str | None = None
    max_tokens: Annotated[int, Field(ge=1)] | None = None


@dataclass(frozen=True)
class NewSearch:
    __pydantic_config__ = STRICT

    question: Annotated[str, Field(min_length=1, max_length=2000)]
    k: Annotated[int, Field(ge=1, le=100)] = 5


@dataclass(frozen=True)
class ServedModel:
    name: str
    dimensions: int
    default_tokens: int
    max_tokens: int
```

**Archivo nuevo: `src/embeddings/api/routes/models.py`.** Va con `def` (no `async`).

```python
"""GET /models: the embedding models of the project, with their token limits."""

from fastapi import APIRouter

from embeddings.api.schemas import ServedModel
from embeddings.config import MODELS

router = APIRouter(tags=["models"])


@router.get("/models")
def list_models() -> list[ServedModel]:
    return [ServedModel(name, s.dimensions, s.default_tokens, s.max_tokens) for name, s in MODELS.items()]
```

**Archivo nuevo: `src/embeddings/api/routes/config.py`.** `GET` responde `resolve(store)`; `PUT` valida con
`token_limit(model, max_tokens)` (un modelo fuera de `MODELS` → 422) y guarda con `origin="manual"`; `PATCH` mezcla con
la activa; `DELETE` la borra (vuelve a la de por defecto).

**Archivo nuevo: `src/embeddings/api/routes/search.py`.** (048: se reemplazó por `api/routes/vectors.py`.) Esta ruta
solo convierte la pregunta en vector, con el modelo de la configuración activa (el índice depende del modelo); el Cypher
está en `data`.

```python
"""POST /search: the official fragments closest to a question."""

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool

from embeddings.api.dependencies import Embedding, Session
from embeddings.api.schemas import NewSearch
from embeddings.config import CHUNK_LABEL
from embeddings.domain import resolve, token_limit, vector_index
from embeddings.models import SearchHit

router = APIRouter(tags=["search"])


@router.post("/search")
async def search(embedder: Embedding, session: Session, body: NewSearch) -> list[SearchHit]:
    model = (await run_in_threadpool(resolve, session.config)).model
    limit = token_limit(model, None)  # a question is short: the model's default
    vector = (await run_in_threadpool(embedder.embed, model, [body.question], limit))[0]  # never in the loop
    index = vector_index(CHUNK_LABEL, model).name
    return await run_in_threadpool(session.vectors.search, index, vector, body.k)
```

**Archivo nuevo: `src/embeddings/api/routes/runs.py`.** Sigue la forma de las corridas de `chunking` (`POST /chunking/runs`, 045):
resuelve la configuración activa **al encolar** y la guarda en la corrida, así cambiarla después no afecta a una en
curso.

```python
"""POST /runs, GET /runs and GET /runs/{id}."""

from fastapi import APIRouter, HTTPException, Response, status

from embeddings.api.dependencies import Embedding, Registry, Settings
from embeddings.api.schemas import NewRun
from embeddings.api.worker import launch, simulated
from embeddings.domain import resolve
from embeddings.models import EmbeddingRun, RunRequest

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def start_run(
    registry: Registry, settings: Settings, embedder: Embedding, new: NewRun, response: Response
) -> EmbeddingRun:
    request = RunRequest(new.sha256s, new.simulate, new.force)
    with settings.session() as session:
        config = resolve(session.config)
    if new.simulate:
        response.status_code = status.HTTP_200_OK
        return simulated(settings, embedder, config, request)
    run = registry.enqueue(config)
    if run is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "the queue is full")
    launch(registry, run, settings, embedder, request)
    return run


@router.get("")
def list_runs(registry: Registry) -> list[EmbeddingRun]:
    return registry.all()


@router.get("/{id}")
def read_run(registry: Registry, id: str) -> EmbeddingRun:
    run = registry.get(id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"there is no run {id!r}")
    return run
```

**Archivo nuevo: `src/embeddings/api/routes/experiments.py`.** Igual que `runs.py`, con `NewExperiment` →
`ExperimentRequest` (`token_limit(model, max_tokens)` antes de encolar: 422) y `ExperimentRunner`; más `apply`.

**Archivo nuevo: `src/embeddings/api/routes/health.py`.** Dice si el extra está instalado sin cargar el modelo
(`importlib.util.find_spec("transformers")` y `"torch"`) y si `data` contesta (`common.http.responds`).

## A9. La app, el registro y el trabajador

> **Viene de:** [`load_fragments.py` L59-137](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/load_fragments.py#L59-L137)
> (lo que corría en primer plano ahora va en un hilo, con estado consultable). Forma: `src/chunking/api/runs/`.

**Archivo nuevo: `src/embeddings/api/registry.py`.** Corridas y experimentos en memoria con un lock, **en una fila**
como la `WorkQueue` de `chunking` (039): `enqueue(config)` devuelve `None` si ya hay `MAX_WAITING` esperando (409), y
se procesan de a uno (el modelo es uno solo). Copia `src/chunking/api/work_queue.py` y su registro. Las corridas se
pierden al reiniciar, pero los vectores no se recalculan: la huella sigue igual. Si hace falta el historial, `chunking`
lo resolvió con `CORRIDA_CHUNKING`.

**Archivo nuevo: `src/embeddings/api/worker.py`.** El hilo de cada corrida. Registra con `logging`, nunca con texto de
los documentos.

```python
"""Runs one embedding run in its own thread: it calls this same server, so it never runs in the event loop."""

import logging
import threading

from embeddings.adapters import HttpSession
from embeddings.domain import Runner
from embeddings.models import (
    DocumentFailure, Embedder, EmbeddingConfig, EmbeddingRun, RunProgress, RunRequest, UpstreamDown,
)

from .dependencies import ApiSettings
from .registry import RunRegistry

LOG = logging.getLogger(__name__)


def _ignore(_: object) -> None:
    pass


def simulated(settings: ApiSettings, embedder: Embedder, config: EmbeddingConfig, request: RunRequest) -> EmbeddingRun:
    """What a run would do. Nothing is stored and no run is registered."""
    with settings.session() as session:
        progress = Runner.run(session.source, session.vectors, embedder, config, request, _ignore, _ignore, _ignore)
    return EmbeddingRun.simulated(config, progress)


def _failed(registry: RunRegistry, run: str, failure: DocumentFailure) -> None:
    LOG.warning("embedding run %s: document %s failed: %s", run, failure.sha256, failure.error)
    registry.failure(run, failure)


def launch(
    registry: RunRegistry, run: EmbeddingRun, settings: ApiSettings, embedder: Embedder, request: RunRequest
) -> None:
    def execute() -> None:
        LOG.info("embedding run %s started", run.id)
        try:
            with settings.session() as session:
                progress = Runner.run(
                    session.source,
                    session.vectors,
                    embedder,
                    run.config,  # resolved when it was queued
                    request,
                    lambda p: registry.progress(run.id, p),
                    lambda f: _failed(registry, run.id, f),
                    lambda sha256: registry.embedded(run.id, sha256),
                )
        except UpstreamDown as error:  # the machine, not a document: nothing else is written
            LOG.error("embedding run %s stopped: %s", run.id, error)
            registry.finish(run.id, RunProgress(), str(error))
            return
        except Exception as error:  # a bug must not leave it "running" forever (and block the next ones)
            LOG.exception("embedding run %s failed", run.id)
            registry.finish(run.id, RunProgress(), f"{type(error).__name__}: {error}")
            return
        LOG.info("embedding run %s finished: %s", run.id, progress)
        registry.finish(run.id, progress, None)

    threading.Thread(target=execute, name=f"embeddings-{run.id}", daemon=True).start()
```

**Archivo nuevo: `src/embeddings/api/processes.py`.** Implementa `common.processes.ProcessSource`: cada corrida como
`ProcessFacts` para el tablero. Copia `src/chunking/api/processes.py`.

**Archivo nuevo: `src/embeddings/api/dependencies.py`.** `ApiSettings(self_url, data_path)` (solo `data`: no conoce otro módulo) con
`session()` (como en `chunking`) y las dependencias `Settings`, `Registry`, `Embedding` (el `LocalModels` de la app) y
`Session` (una `HttpSession` por petición).

**Archivo nuevo: `src/embeddings/api/app.py`.**

```python
"""embeddings HTTP API, mounted by server at /embeddings: the only module that loads embedding models."""

from fastapi import FastAPI

from common.api import error_handlers, process_router
from embeddings.adapters import LocalModels
from embeddings.models import DocumentError, InvalidLimit, UpstreamDown

from .app_info import VERSION
from .dependencies import ApiSettings
from .processes import EmbeddingProcesses
from .registry import RunRegistry
from .routes import ROUTERS


def create_app(settings: ApiSettings) -> FastAPI:
    app = FastAPI(title="prueba-chunking · embeddings", version=VERSION, description="Vectors of texts and chunks.")
    app.state.settings = settings
    app.state.embedder = LocalModels()  # one for the app: every model stays loaded between requests
    app.state.registry = RunRegistry()
    app.state.processes = EmbeddingProcesses(app.state.registry)
    error_handlers(app, {UpstreamDown: 503, DocumentError: 502, InvalidLimit: 422})
    app.include_router(process_router(lambda connection: [connection.app.state.processes]))
    for router in ROUTERS:
        app.include_router(router)
    return app
```

## A10. Montarlo en el servidor

**Archivo modificado: `src/server/app.py`.**

```python
from common.config import DATA_PATH, EMBEDDINGS_PATH
from embeddings.api import ApiSettings as EmbeddingsSettings
from embeddings.api import create_app as embeddings_app

EMBEDDINGS = EMBEDDINGS_PATH

# dentro de create_app:
embeddings = embeddings_app(EmbeddingsSettings(settings.self_url, DATA))
sources = [..., embeddings.state.processes]  # junto a los de ingesta, parsing, chunking y pipeline
app.mount(EMBEDDINGS, embeddings)
```

Y en `health()`, dentro de `modules`:

```python
EMBEDDINGS.strip("/"): OK,  # nothing to open; GET /embeddings/health checks the model and data
```

Suma también su `/docs` a la `description` de la app raíz. El `HostGuard` y el `BodyLimit` de la raíz lo protegen sin
hacer nada más.

---

# Parte B. Lo que pasa en `chunking`

**Nada que hacer desde esta guía.** La versión anterior hacía que `semantic` le pidiera los vectores a
`POST /embeddings/vectors`. Con la reorganización:

- La **043** quita de `chunking` todas sus estrategias propias (`adapters/strategies/`, `semantic` incluida), sus
  embeddings (`embeddings.py`, `EMBEDDING_MODELS`, `EMBEDDING_CACHE`, `EMBEDDING_BATCH`, `SIMILARITY_THRESHOLD`) y sus
  tests. Chunking solo usa los chunkers de Docling (`hybrid`, `hierarchical`, `page`).
- `chunking` **no llama a `embeddings`** ni sabe que existe. Probar chunking y embeddings juntos es el laboratorio del
  pipeline (044): un experimento de chunking, después uno de embeddings sobre él, y `lab` puntúa el par.
- Lo único que se aprovecha de `chunking` es el código del modelo (`_Embedder`, `pretrained`), que A5 **copia** antes de
  que la 043 lo borre. Si la 043 ya está en `main`, sale del historial de git
  (`git show <commit anterior>:src/chunking/adapters/strategies/embeddings.py`).

Comprobación de que `chunking` no carga modelos de vectores (debe salir vacío, después de la 043):

```bash
grep -rn "AutoModel\|_Embedder\|EMBEDDING_CACHE\|EMBEDDING_MODELS\|embeddings" src/chunking
```

---

# Parte C. Consola, pipeline, tests y documentación

## C1. Que aparezca en la consola

**Archivos modificados en `src/server/console/`:**

| Archivo          | Qué agregar                                                                                                                            |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `catalog.py`     | `Module("embeddings", "/embeddings")` en `MODULES`                                                                                     |
| `texts.py`       | Nombre y efecto en español del módulo, de cada recurso y de cada ruta. Un test falla si falta uno                                      |
| `progress.py`    | `POST /runs` → `/embeddings/runs/{id}` y `POST /experiments` → `/embeddings/experiments/{id}` en `WATCHED`, para ver el avance en vivo |
| `bodies.py`      | Plantillas de `POST /runs`, `POST /experiments`, `PUT /config` y `POST /search`, con `simulate` donde aplica                            |
| `suggestions.py` | `model`: valores de `GET /embeddings/models`; `sha256s`: los `JSON` chunkeados de `data`; `chunking_experiment`: los experimentos de chunking terminados (de `data`) |

Las rutas aparecen solas porque salen del `openapi.json`. Más detalle en [guia-consola.md](guia-consola.md).

## C2. Conectarlo al pipeline

Lo hace la **044** (`spec/features/044-pipeline-produccion-y-laboratorio/`), no esta guía: el pipeline tiene un
cliente de `embeddings` y tres acciones. Ya no hay un actor `embeber`: `embeddings` es un módulo.

| Plantilla     | Paso                     | Qué llama                                                                                     |
| ------------- | ------------------------ | --------------------------------------------------------------------------------------------- |
| `produccion`  | embeber (último)         | `POST /embeddings/runs {sha256s}` con los que `chunking` acaba de chunkear → espera `finished` |
| `laboratorio` | 3b, dentro del ciclo     | `POST /embeddings/experiments {chunking_experiment, model, max_tokens}` → espera              |
| `laboratorio` | aplicar (al aprobar)     | `POST /embeddings/experiments/{id}/apply` (junto al `apply` de chunking)                      |
| las dos       | antes de lanzar el ciclo | `GET /embeddings/models`: el `tokenizer` de chunking = `model`; `max_tokens` de chunking ≤ límite − 2 |

Lo que el pipeline espera de este módulo (el contrato de la 044): que `GET /runs/{id}` y `GET /experiments/{id}` den
`status` (`queued`, `running`, `finished`, `failed`) y la lista de `sha256` hechos, y que una fila llena sea un 409
(el pipeline lo reintenta). Las rutas exactas quedan en constantes del pipeline: si aquí cambian, se ajustan allá.

Para probarlo a mano, sin el pipeline:

```bash
curl -XPOST localhost:8000/embeddings/runs -H 'Content-Type: application/json' -d '{"sha256s": ["<sha256>"]}'
curl localhost:8000/embeddings/runs/<id>
```

## C3. Tests

Usa nombres que no existan ya: mypy falla con dos archivos de test iguales (`test_runner.py`, `test_mappers.py`,
`test_health.py` están en uso).

| Archivo                                                                    | Qué comprueba, un comportamiento por test                                                                                                                                                                                         |
| -------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/embeddings/domain/test_embedding_runner.py`                         | Lo que no cambió no se recalcula; `force` sí; no chunkeado, `parcial` o `error` se omiten; un `sha256` sin `JSON` cuenta como `missing`; un chunk más largo que el límite falla solo su documento sin escribir; el límite queda en `limite_tokens_embedding`; `UpstreamDown` corta y no escribe; `simulate` no escribe |
| `tests/embeddings/domain/test_embedding_experiments.py`                    | Embebe los `EXP_CHUNK` del experimento; nunca escribe el `JSON` oficial; un experimento que no existe → 404; `apply` copia modelo y límite a la activa                                                                             |
| `tests/embeddings/domain/test_active_config.py`                            | Sin guardada, `DEFAULT_MODEL` con su `default_tokens`; una guardada con un modelo que ya no está → la de por defecto                                                                                                               |
| `tests/embeddings/domain/test_limits.py`                                   | Sin pedir, `default_tokens`; un valor dentro del rango se respeta; 0 o más que `max_tokens` → `InvalidLimit`                                                                                                                      |
| `tests/embeddings/domain/test_fingerprint.py`                              | Cambia con el texto, el modelo y la versión                                                                                                                                                                                       |
| `tests/embeddings/domain/test_batches.py`                                  | Todo en `merge`, sin `replace_from`; un experimento no lleva el `JSON`                                                                                                                                                            |
| `tests/embeddings/domain/test_indexes.py`                                  | El nombre del ejemplo; el mismo modelo da el mismo nombre; otro modelo, otra dimensión u otra etiqueta dan otro; solo `[a-z0-9_]` y empieza con `vec_`                                                                           |
| `tests/embeddings/config/test_data_names.py`                               | Cada etiqueta de `config` (`JSON`, `SECCION`, `FRAGMENTOS`, `EXPERIMENTO`, `EXP_SECCION`, `EXP_CHUNK`, `CONFIG_OFICIAL`) está en el esquema de `data` (`GET /data/schema` con `MockTransport` o el enum de `data` desde `tests/`) |
| `tests/embeddings/adapters/test_text_embedder.py`                          | **Copiado** de `tests/chunking/adapters/strategies/test_embeddings.py` (el `monkeypatch` apunta a `embeddings.adapters.text_embedder`); además, el `max_length` de cada llamada llega al tokenizador                              |
| `tests/embeddings/adapters/test_local_models.py`                           | Un modelo se carga una vez; no poder cargarlo da `UpstreamDown`                                                                                                                                                                   |
| `tests/embeddings/adapters/test_chunks_client.py`, `test_vector_client.py` | Con `httpx.MockTransport`: recorre `JSON → SECCION → FRAGMENTOS` en orden; 5xx → `UpstreamDown`; 4xx → `DocumentError`; ids correctos                                                                                            |
| `tests/embeddings/api/routes/test_embedding_runs.py`, `test_search.py`     | 202, 200 con `simulate`, `sha256s` vacía → 422, fila llena → 409, 404, claves desconocidas → 422; la corrida guarda la configuración con que se encoló                                                                             |
| `tests/embeddings/api/routes/test_embedding_config.py`                     | `GET` sin guardada da la de por defecto; `PUT` con modelo desconocido o límite fuera de rango → 422; `PATCH` cambia solo lo que viene; `DELETE` vuelve al defecto                                                                 |
| `tests/embeddings/integration/test_real_model.py`                          | Con `@pytest.mark.embed`: 384 dimensiones, norma 1, `tokens`, y que `MODELS[...].max_tokens` no pase de las posiciones del modelo real                                                                                             |
| `tests/data/api/routes/test_vectors.py`                                    | Nombre o dimensiones inválidos → 422 sin tocar el grafo; una etiqueta que no es de chunks → 422; índice existente con otra definición → 409; búsqueda en un índice que no existe → 404; dimensión del vector distinta → 422       |
| `tests/data/repository/test_vector_repository.py`                          | Con `@pytest.mark.neo4j`: crear el índice y que repetirlo no cambie nada, búsqueda, excluye lo que no tenga `estado_chunking: fragmentado`, `merge` conserva el texto                                                             |
| `tests/common/` (regla de los módulos, 042)                                | `src/embeddings/` no nombra rutas de otro módulo que no sea `data`                                                                                                                                                                |

Lo que más hay que proteger, porque son errores que ya ocurrieron en este proyecto:

1. Un fallo de la máquina (modelo, `data`) no marca ningún documento como erróneo.
2. Un chunk largo nunca se trunca sin avisar al embeber.
3. Guardar vectores no borra nada.
4. Un experimento nunca escribe en lo oficial.

Registra el marcador `embed` en `[tool.pytest]` de `pyproject.toml` (el test se omite sin el extra), y en
`.github/workflows/ci.yml` suma `--extra embed` al paso de auditoría.

## C4. Archivos `http/` y documentación

- **Archivos nuevos:** `http/embeddings/info.http` (health, models y config), `runs.http`, `experiments.http` y
  `search.http` (048: hoy `vectors.http`); `http/connections/embeddings-data.http` (lo que `embeddings` lee y escribe en
  `data`).
- **Archivos modificados:** `docs/arquitectura.md` (el paquete y la regla de los módulos), `docs/api.md` (las rutas),
  `docs/README.md` y `CLAUDE.md` (sección del paquete y los extras).

## C5. Verificar

```bash
uv sync --extra data --extra chunk --extra embed     # uv sync quita los extras que no se nombren
uv run ruff format && uv run ruff check && uv run mypy && uv run pytest

NEO4J_PASSWORD=... uv run prueba-chunking serve
curl localhost:8000/health                      # embeddings aparece en "modules"
curl localhost:8000/embeddings/health           # modelo y data
curl localhost:8000/embeddings/models
curl localhost:8000/embeddings/config           # la de por defecto: el modelo multilingüe con 128

# Producción a mano (lo que hará el pipeline): unos sha256 que chunking ya chunkeó.
curl -XPOST localhost:8000/embeddings/runs -H 'Content-Type: application/json' -d '{"sha256s": ["<sha256>"], "simulate": true}'
curl -XPOST localhost:8000/embeddings/runs -H 'Content-Type: application/json' -d '{"sha256s": ["<sha256>"]}'
curl localhost:8000/embeddings/runs/<id>
# Repetir la misma corrida: ahora todo debe salir en `unchanged`.

# Laboratorio a mano: sobre un experimento de chunking terminado.
curl -XPOST localhost:8000/embeddings/experiments -H 'Content-Type: application/json' \
  -d '{"name": "minilm 128", "chunking_experiment": "<id>", "model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"}'
curl localhost:8000/embeddings/experiments/<id>
curl -XPOST localhost:8000/embeddings/experiments/<id>/apply

# Desde la 048: la búsqueda es de consultas; embeddings solo da el vector.
curl -XPOST localhost:8000/consultas/search -H 'Content-Type: application/json' \
  -d '{"question": "¿Qué temas se ven en el PIAA de Bases de Datos?", "k": 5}'
curl -XPOST localhost:8000/embeddings/vectors -H 'Content-Type: application/json' -d '{"texts": ["Bases de Datos"]}'
```

Para probar sin riesgo, usa un Neo4j temporal, otro puerto y una copia de la memoria:

```bash
docker run -d --rm --name embeddings-prueba -p 17690:7687 -e NEO4J_AUTH=neo4j/<clave> neo4j:2026.07.1
NEO4J_PASSWORD=<clave> uv run prueba-chunking serve --neo4j-url neo4j://localhost:17690 --port 18003 --memory <copia>
docker rm -f embeddings-prueba    # al terminar
```

Comprueba también las fronteras: agrega `import data` en `src/embeddings/domain/` y mira que `ruff check` lo rechace; y
que el `grep` de la Parte B salga vacío.

## Decisiones pendientes

| Decisión                     | Por qué importa                                                                                                                                                                                                                                                          | Recomendación                                                                                                                                                                               |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Varios modelos a la vez      | **Resuelto en la 055 (parte a):** una propiedad por modelo (`embedding_<modelo>_<dim>`), validada en `data`, con su índice; se cambia de modelo sin cortar el chat | Falta que chunking admita los tokenizadores de los candidatos (`TOKENIZERS`) y cuente el prefijo `passage: ` de e5 |
| Límite de tokens por defecto | Por encima de `default_tokens` (128) el modelo funciona, pero no se entrenó con textos tan largos; por debajo, poco contexto por chunk                                                                                                                                   | Medir con un experimento y unas preguntas de referencia qué `max_tokens` da mejores resultados antes de procesar todo; si ninguno sirve, otro modelo (otra línea en `MODELS` y otro índice) |
| Tokens especiales            | El modelo cuenta `[CLS]` y `[SEP]`; `chunking` no                                                                                                                                                                                                                        | El pipeline pone `chunking.max_tokens = límite − 2` (044); a mano, la misma cuenta                                                                                                          |
| Lectura de chunks            | Bajar los chunks de un documento son varias llamadas a `data` (A7)                                                                                                                                                                                                      | Dejarlo así; si pesa, una lectura en profundidad en `data`                                                                                                                                  |
| Fragmentos citados           | `piaa-rag` marca `obsoleto` los que cita una `CONSULTA` o un `HALLAZGO` ([`Q_RETIRE`](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/load_fragments.py#L41-L51)); aquí `replace_from` los borra al refragmentar | Decidirlo junto con el tema pendiente de `HALLAZGOS`, antes de tener consultas reales                                                                                                       |
| Documentos parciales         | Sus chunks no se embeben hasta que estén completos                                                                                                                                                                                                                       | Dejarlo así                                                                                                                                                                                 |
| Autenticación                | `POST /search`, `/runs` y `/experiments` quedan abiertos                                                                                                                                                                                                                     | Igual que el resto: resolver si el servidor se expone                                                                                                                                       |
| Memoria de Neo4j             | `piaa-rag` le da 2 GB de heap y 1 GB de page cache ([`docker-compose.yml` L10-11](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/docker-compose.yml#L10-L11)); aquí no se fija y el índice vectorial consume memoria       | Medir con el corpus real                                                                                                                                                                    |

## Fuera de esta guía

- **Imágenes y CLIP.** [`load_images.py`](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/load_images.py)
  está vacío y la búsqueda de imágenes ([`search.py` L31-49](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/embeddings/search.py#L31-L49))
  depende de él; aquí las imágenes solo se conservan por su leyenda. Requiere extraerlas primero y un cargador de CLIP;
  sería otra línea en `MODELS` y otro índice en A6.
- **Búsqueda de texto completo e híbrida.** Los índices `FULLTEXT` en español de
  [`001_schema.cypher` L55-64](https://github.com/jeronimo-taborda-e/piaa-rag/blob/f6368cda6c38c10cb035937e71d46145e0b70398/scripts/001_schema.cypher#L55-L64)
  se pueden añadir con el mismo patrón de A6.
- **Generar respuestas con un modelo de lenguaje.** Este módulo termina al devolver fragmentos.
