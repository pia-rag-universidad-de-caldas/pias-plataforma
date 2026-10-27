# Guía: configurar chunking o cambiar su configuración

Qué se puede configurar en `src/chunking/`, dónde y qué pasa al cambiarlo. Hay tres niveles:

1. **Por petición**: cada corrida o experimento manda sus parámetros en el cuerpo. No se toca código.
2. **Valores por defecto y límites**: `src/chunking/config/settings.py`. Lo que se usa cuando la petición no dice nada,
   y lo que se permite pedir.
3. **Parámetros nuevos**: un parámetro que hoy no existe. Toca modelos, lo guardado en el grafo, la API y tests.

## Antes de cambiar nada: el fingerprint

Cada documento fragmentado se guarda en el grafo con el **fingerprint** de sus parámetros (un hash de todos:
`tokenizer`, `max_tokens`, `merge_peers`, `repeat_table_header`, `table_structure`, `table_mode` y la versión de
Docling; `ChunkingParameters.fingerprint`). Una corrida por páginas solo procesa los documentos **pendientes**: nuevos,
con otro contenido o **con otro fingerprint** (`Selection.is_pending`).

Consecuencia: **cambiar un valor por defecto de chunking deja pendiente todo el corpus** (unos 8900 documentos), y la
próxima `POST /chunking/runs` sin `limit` los vuelve a fragmentar todos. Actualizar Docling hace lo mismo. Probar antes
con `{"simulate": true}`, que solo cuenta cuántos procesaría (ver «Verificar»).

Las conversiones de los experimentos tienen su propio fingerprint (`ConversionParameters.fingerprint`): con los mismos
parámetros de conversión se reutilizan; con otros, se convierte de nuevo con Docling (lento).

## 1. Por petición (sin tocar código)

### Corridas de producción: `POST /chunking/runs`

```json
{
  "limit": 10,
  "simulate": false,
  "types": ["pdf"], "year": 2024,
  "parameters": {
    "tokenizer": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "max_tokens": 256,
    "merge_peers": true,
    "repeat_table_header": false,
    "table_structure": true,
    "table_mode": "fast"
  }
}
```

Lo que falta toma el valor por defecto. Validación: `max_tokens` en `MAX_TOKENS_RANGE`, `tokenizer` dentro de
`TOKENIZERS` (si no, 422). Cuerpo en `api/runs/schemas.py` (`RunParameters`); se arma en `api/routes/runs.py`. Para
refragmentar documentos concretos con otros parámetros: `"sha256s": [...]` (ignora los filtros y procesa aunque ya
estén hechos).

### Experimentos: `POST /chunking/experiments`

- `conversion`: `heading_level` (1–6), `numbered_titles`, `table_structure`, `table_mode` e `include` (`tables`,
  `lists`, `page_headers`, `page_footers`, `pictures`). Cuerpo: `ConversionBody` en `api/experiments/schemas.py`.
- `plan.rules[].chunking` y `plan.default`: la estrategia de cada sección (`strategy`: `hybrid`, `element`, `section`,
  `page`, `fixed`, `points`, `semantic`) con sus parámetros. **Cada estrategia acepta solo los suyos** (tabla `USES` en
  `domain/experiments/parameters.py`); mandar uno que no usa da 422, nunca se ignora en silencio:

  | Estrategia | Además de `tokenizer` |
  |---|---|
  | `hybrid` | `max_tokens`, `merge_peers` |
  | `element` | — (no parte: un chunk por elemento) |
  | `section`, `page`, `points` | `max_tokens` |
  | `fixed` | `max_tokens`, `overlap_tokens` |
  | `semantic` | `max_tokens`, `embedding_model`, `similarity_threshold` |

Ejemplos completos en `http/chunking/experiments.http`.

## 2. Valores por defecto y límites: `config/settings.py`

Después de cambiar un valor: reiniciar el servidor (se lee al arrancar). Si es un nombre nuevo, exportarlo también en
`config/__init__.py`.

| Grupo | Constantes | Qué pasa al cambiarlas |
|---|---|---|
| Chunking de producción | `MAX_TOKENS`, `TOKENIZER`, `MERGE_PEERS`, `REPEAT_TABLE_HEADER`, `TABLE_STRUCTURE`, `TABLE_MODE` | **todo queda pendiente** (fingerprint). `REPEAT_TABLE_HEADER=True` puede dar chunks de más de `max_tokens`: esos documentos terminan en error (nunca se guardan) |
| Límites de lo que se puede pedir | `MAX_TOKENS_RANGE`, `TOKENIZERS`, `EMBEDDING_MODELS` | nada se reprocesa; cambia lo que la API acepta |
| Estrategias de experimentos | `STRATEGY`, `OVERLAP_TOKENS`, `EMBEDDING_MODEL`, `SIMILARITY_THRESHOLD`, `EMBEDDING_BATCH` | solo los experimentos nuevos |
| Conversión de experimentos | `HEADING_LEVEL`, `NUMBERED_TITLES` | solo los experimentos nuevos (otra conversión: no se reutiliza la vieja) |
| Puntuaciones | `SCORE_CRITERIA`, `SCORE_MIN`, `SCORE_MAX` | los criterios que siempre salen en el resumen y el rango válido |
| Tiempos | `DOCUMENT_TIMEOUT` (Docling por documento), `RUN_TIMEOUT` (cada petición a otro módulo en una corrida), `HTTP_TIMEOUT` (health) | un PDF enorme que se corta por tiempo queda en error |
| Páginas | `CHUNK_PAGE_SIZE`, `GRAPH_PAGE_SIZE`, `PER_PAGE`, `MAX_PER_PAGE`, `SELECTION_MAX_PER_PAGE` | `GRAPH_PAGE_SIZE` y `SELECTION_MAX_PER_PAGE` no pueden pasar el `MAX_PER_PAGE` de data (500) |
| Dónde están los otros | `INGESTA_PATH`, `DATA_PATH`, `SELF_URL` | solo si el servidor los monta en otro prefijo (`server/app.py`) |
| Cachés | `TOKENIZER_CACHE`, `EMBEDDING_CACHE` (relativas a la raíz) | se bajan de nuevo la primera vez |
| Grafo | `UNASSIGNED_CODE` | debe ser el mismo que el de ingesta (`000000`) |

### Recetas

**Permitir otro tokenizador.** Agregarlo a `TOKENIZERS`. Solo los nombres de esa lista llegan al Hub de Hugging Face
(nunca un texto de la petición): es una medida de seguridad, no quitarla. La primera corrida que lo pida lo baja a
`.cache/tokenizers`; después se lee sin red.

**Permitir otro modelo de embeddings** (estrategia `semantic`). Agregarlo a `EMBEDDING_MODELS`. Se baja una vez a
`.cache/embeddings` y corre local (`transformers` + `torch`, del extra `chunk`).

**Cambiar el `max_tokens` por defecto.** Cambiar `MAX_TOKENS` y avisar que la próxima corrida completa refragmenta
todo. Si solo se quiere probar, mejor pedirlo por petición (`"parameters": {"max_tokens": 256}`) con `limit` o con
`sha256s`, y dejar el valor por defecto.

**Cambiar los criterios de puntuación de prueba.** `SCORE_CRITERIA`. Los criterios son libres (cualquier nombre en
`SCORE_MIN`–`SCORE_MAX`); estos son los que el resumen muestra siempre, aunque nadie los haya puntuado.

## 3. Un parámetro nuevo

### En las corridas de producción

Un parámetro de producción se guarda en cada `JSON` del grafo y entra en el fingerprint. En orden:

1. `models/concepts.py`: el campo en `ChunkingParameters` (entra solo en `fingerprint`, que hashea todos los campos).
2. `config/settings.py` (+ `config/__init__.py`): su valor por defecto.
3. Lo guardado (`models/stored.py`): la clave en `ParametersProperties`, **en español** (es una propiedad del grafo).
4. Quien lo escribe: `Hierarchy.parameters` (`domain/production/hierarchy.py`).
5. Quien lo lee: `parameters` en `adapters/data/mappers.py`. Los `JSON` viejos no lo tienen: decidir qué hacer (hoy
   un valor que falta deja `parameters` en `None`, y el documento queda pendiente por su fingerprint distinto).
6. La API: el campo en `RunParameters` (`api/runs/schemas.py`, con su validación) y donde se arma
   `ChunkingParameters` (`api/routes/runs.py`).
7. Quien lo usa: `DoclingConverter.chunk` (`adapters/docling_converter.py`). Si cambia cómo se construye el
   `HybridChunker` o el `DocumentConverter`, incluirlo en la clave de su caché (se reusan por parámetros).
8. Tests: la ida y vuelta escribir → leer en `tests/chunking/adapters/data/test_stored_shapes.py`
   (`test_what_hierarchy_writes_is_what_the_mapper_reads`), y `test_parameters_need_every_value` en
   `test_graph_clients.py`.
9. `http/chunking/runs.http`, `CLAUDE.md` (la lista de propiedades del `JSON`).

### En una estrategia de experimentos

1. `models/concepts.py`: el campo en `StrategyParameters`; `models/requests.py`: en `RequestedStrategy`.
2. `domain/experiments/parameters.py`: sumarlo a `USES` de las estrategias que lo usan y resolverlo en
   `Parameters.resolve` (valor por defecto de `config` y validación; un valor inválido es `InvalidParameters` → 422).
3. `api/experiments/schemas.py`: el campo en `StrategyBody`; `api/experiments/requests.py`: pasarlo en `_strategy`.
4. La estrategia que lo usa, en `adapters/strategies/<estrategia>.py`.
5. Tests en `tests/chunking/domain/experiments/test_parameters.py`: que se aplique el valor por defecto, que se rechace
   en una estrategia que no lo usa y que se valide su rango.

Una estrategia nueva entera: su valor en `ChunkingStrategy`, su archivo en `adapters/strategies/` (registrado en
`STRATEGIES`, `adapters/strategies/__init__.py`), su línea en `USES` y sus tests.

## Docling

Docling es el extra `chunk` (arrastra PyTorch, ~6 GB). Sin él todo arranca, `GET /chunking/health` dice
`docling: missing` y lo que necesita convertir responde 503. Se suele instalar en un entorno aparte:

```bash
UV_PROJECT_ENVIRONMENT=$HOME/.cache/prueba-chunking-chunk-venv uv sync --extra chunk --extra data
NEO4J_PASSWORD=... $HOME/.cache/prueba-chunking-chunk-venv/bin/prueba-chunking serve
```

Actualizar Docling cambia `docling_version`, que está en ambos fingerprints: deja pendiente todo y obliga a convertir
de nuevo en los experimentos.

## Verificar

```bash
uv run ruff format && uv run ruff check && uv run mypy && uv run pytest
curl localhost:8000/chunking/health
curl -XPOST localhost:8000/chunking/runs -H 'Content-Type: application/json' -d '{"simulate": true}'   # → {"id": ...}
curl localhost:8000/chunking/runs/<id>   # al terminar: progress.pending = cuántos procesaría, progress.skipped = ya hechos
# el fingerprint de la respuesta es el de la configuración nueva
```
