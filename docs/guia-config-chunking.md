# Guía: configurar chunking o cambiar su configuración

Qué se puede configurar en `src/chunking/` (features 043 y 045), dónde y qué pasa al cambiarlo. Chunking ya no
convierte documentos (eso es `parsing`, con una configuración fija) ni tiene estrategias propias: parte el
`DoclingDocument` que `parsing` dejó en cada `JSON` con los chunkers de docling-core. Hay tres niveles:

1. **Por petición y configuración activa**: un experimento lleva su configuración en el cuerpo; las corridas oficiales
   usan la configuración activa, que se cambia por la API. No se toca código.
2. **Valores por defecto, límites y lo fijo**: `src/chunking/config/docling.py` (y `settings.py` para lo técnico).
3. **Parámetros nuevos**: un parámetro que hoy no existe. Toca modelos, lo guardado en el grafo, la API y tests.

## Antes de cambiar nada: las huellas

Todo lo que decide cómo se parte un documento está en `ChunkingParameters` (`models/concepts.py`): `chunker`,
`tokenizer`, `max_tokens`, `merge_peers`, `CHUNKING_VERSION` y la versión de docling-core. Su `fingerprint` es un hash
de **todos**. Al chunkear, en el `JSON` se guardan:

| Propiedad del `JSON` | Qué es |
|---|---|
| `config_chunking` | el `fingerprint` de los parámetros |
| `parseo_chunkeado` | el `fingerprint_parseo` del parseo sobre el que se chunkeó |
| `huella_chunking` | `chunked_fingerprint`: parámetros + parseo |

Una corrida salta el documento cuya `huella_chunking` ya es la de sus parámetros sobre su parseo actual: **un
documento nunca se chunkea dos veces con la misma configuración**. `GET /data/progress/chunking?fingerprint=<huella>`
cuenta como hecho solo lo chunkeado con esa configuración sobre el parseo actual.

Consecuencias:

- **Cambiar la configuración activa** no reprocesa nada solo, pero deja **todo el corpus como faltante** para esa
  configuración: la próxima `POST /chunking/runs` sin `sha256s` lo vuelve a chunkear (y reemplaza sus `SECCION`/
  `FRAGMENTOS`). Probar antes con un experimento, o con `{"simulate": true}`.
- **Parsear de nuevo** un documento (otra versión de `parsing`) borra sus chunks oficiales y cambia su
  `fingerprint_parseo`: queda faltante.
- **Subir `CHUNKING_VERSION` o actualizar docling-core** cambia todos los fingerprints: todo queda faltante.
- Una corrida retomada (`POST /chunking/runs/{id}/resume`) usa la configuración de la corrida: 409 si la activa ya es
  otra.

## 1. Por petición y configuración activa (sin tocar código)

Lo configurable son cuatro campos (`ChunkingBody`, `api/schemas.py`). Lo que no viene toma `CHUNKING_DEFAULT`:

| Campo | Valores | Por defecto | Con qué chunker |
|---|---|---|---|
| `chunker` | `hybrid`, `hierarchical`, `page` | `hybrid` | — |
| `tokenizer` | los de `TOKENIZERS` | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | todos (cuenta los tokens de cada chunk) |
| `max_tokens` | `MAX_TOKENS_RANGE` (16–8192) | 126 | solo `hybrid` |
| `merge_peers` | `true`/`false` | `true` | solo `hybrid` |

| `fit` (062) | `[{tokenizer, max_tokens}, …]`, 1 o más, sin repetir | — | solo `hybrid`; no con `tokenizer` ni `max_tokens` |

Con `fit`, cada chunk cabe en **cada** tokenizador con su presupuesto (un tokenizador compuesto cuenta
`max_i ceil(count_i · B / b_i)`, con `B = min b_i`); `tokens` es el del primero y `tokens_por_tokenizador` guarda los
de todos. `fit` entra en la huella; sin él, las huellas son las de antes.

`max_tokens` o `merge_peers` con `hierarchical` o `page` dan 422: nunca se ignora un parámetro en silencio
(`Parameters.resolve`, `domain/parameters.py`). Un `tokenizer` fuera de la lista, también. Claves desconocidas, 422.

### Experimentos: `POST /chunking/experiments`

```json
{
  "name": "hybrid 256",
  "sha256s": ["<sha256>", "<sha256>"],
  "chunking": {"chunker": "hybrid", "max_tokens": 256, "merge_peers": true},
  "simulate": false
}
```

En lugar de `sha256s`, `"from_experiment": "<id>"` toma los documentos de otro experimento. Los chunks quedan aparte
de lo oficial (`EXPERIMENTO → EXP_SECCION → EXP_CHUNK`) y `GET /chunking/experiments/{id}` da los números (tokens por
chunk, chunks por documento). Ejemplos en `http/chunking/experiments.http`.

### La configuración activa: `/chunking/config`

Es lo que usa `POST /chunking/runs`. Se guarda en un nodo `CONFIG_OFICIAL` (id `activa`) con su `origen`:

```bash
curl localhost:8000/chunking/config                       # la activa, su huella, lo fijo y lo de por defecto
curl 'localhost:8000/chunking/config?documents=true'      # además, cuántos oficiales están hechos con ella (lento)
curl -XPOST localhost:8000/chunking/experiments/<id>/apply   # la de un experimento terminado (origen: experimento)
curl -XPATCH localhost:8000/chunking/config -H 'Content-Type: application/json' -d '{"max_tokens": 200}'   # a mano
curl -XPUT   localhost:8000/chunking/config -H 'Content-Type: application/json' -d '{"chunker": "page"}'   # reemplazar
curl -XDELETE localhost:8000/chunking/config              # volver a la de por defecto
```

- `PATCH` cambia solo lo que viene; pasar de `hybrid` a otro chunker quita `max_tokens` y `merge_peers`.
- Si la guardada ya no sirve (un tokenizador que salió de la lista), se usa la de por defecto y `GET` lo dice en
  `problem`. Si ninguna sirve, `POST /chunking/runs` responde 409.
- En el laboratorio, el pipeline la cambia al aprobar (`chunking.apply`), y además asegura que el `tokenizer` sea el del
  modelo de embeddings y que `max_tokens` quepa en su límite menos 2 (`pipeline/domain/pairing.py`). Chunking no sabe
  de embeddings.

## 2. Valores por defecto, límites y lo fijo: `config/docling.py`

Después de cambiar un valor: reiniciar el servidor (se lee al arrancar). Si es un nombre nuevo, exportarlo también en
`config/__init__.py`.

| Grupo | Constantes | Qué pasa al cambiarlas |
|---|---|---|
| Por defecto | `CHUNKING_DEFAULT` (`chunker`, `tokenizer`, `max_tokens`, `merge_peers`) | cambia la configuración de quien no puso ninguna (origen `defecto`): todo queda faltante para ella |
| Lo que se puede pedir | `CHUNKERS`, `TOKENIZERS`, `MAX_TOKENS_RANGE` | nada se reprocesa; cambia lo que la API acepta (una activa que deja de valer cae a la de por defecto) |
| Lo fijo | `CHUNKING_FIXED` (tablas en tripletas, `repeat_table_header`, capas, imágenes, formato, hipervínculos, `merge_list_items`, `expand`, `always_emit_headings`, `contextualize`) | **subir `CHUNKING_VERSION`**: entra en todos los fingerprints, así que todo queda faltante. El porqué de cada valor está en la spec 043 |

Y en `config/settings.py` (técnico):

| Constante | Qué es |
|---|---|
| `TOKENIZER_CACHE` | dónde se bajan los tokenizadores (`.cache/tokenizers`, relativo a la raíz) |
| `RUN_TIMEOUT` | segundos por petición a `data` durante una corrida o un experimento |
| `GRAPH_PAGE_SIZE` | nodos por página al leer de `data` (no puede pasar el `MAX_PER_PAGE` de data, 500) |
| `SELF_URL` | solo si la app se arma sin servidor (el servidor pone el suyo) |

### Recetas

**Permitir otro tokenizador.** Agregarlo a `TOKENIZERS`. Solo los nombres de esa lista llegan al Hub de Hugging Face
(nunca un texto de la petición): es una medida de seguridad, no quitarla. El primer uso lo baja a `.cache/tokenizers`;
después se lee sin red. Si es para un modelo de embeddings nuevo, ese modelo va en `embeddings/config` (`MODELS`).

**Cambiar el `max_tokens` por defecto.** Cambiar `CHUNKING_DEFAULT.max_tokens`. Debe caber en el límite del modelo de
embeddings por defecto menos 2 (el modelo cuenta `[CLS]` y `[SEP]`; el tokenizador de docling-core no): si no, el
embedding cortaría el chunk y `embeddings` falla ese documento. Para probar, mejor un experimento.

**Cambiar algo de lo fijo.** Cambiar el valor en `CHUNKING_FIXED`, subir `CHUNKING_VERSION` y escribir el porqué en
la spec. Si cambia cómo se construye el chunker, el cambio va en `adapters/docling_chunkers.py` (`_build`, el
serializador de tablas).

## 3. Un parámetro configurable nuevo

Un parámetro configurable se pide en experimentos y en la configuración activa, se guarda en el `JSON` (y en el
`EXPERIMENTO`) y entra en el fingerprint. En orden:

1. `models/concepts.py`: el campo en `RequestedChunking` (como se pide, `None` = no pedido) y en
   `ChunkingParameters` (resuelto; entra solo en `fingerprint`, que hashea todos los campos, y en `configurable()`).
2. `config/docling.py` (+ `config/__init__.py`): su valor en `ChunkingDefault` y, si tiene, su rango o lista.
3. `domain/parameters.py`: resolverlo en `Parameters.resolve` (valor por defecto y validación; un valor inválido, o
   pedido a un chunker que no lo usa, es `InvalidParameters` → 422).
4. La API: el campo en `ChunkingBody` (`api/schemas.py`) y en `requested()`.
5. Lo guardado (`models/stored.py`): la clave en `ChunkingParametersProperties` y en `ConfigProperties`, **en
   español** (es una propiedad del grafo). Quien lo escribe: `parameters_properties` (`domain/sections.py`) y el lote
   de la configuración. Quien lo lee: los mappers de `adapters/data/mappers.py` (`config`, la corrida, el
   experimento). Lo guardado antes no lo tiene: decidir qué significa que falte.
6. Quien lo usa: `DoclingChunkers._build` (`adapters/docling_chunkers.py`). Los chunkers se reusan por `fingerprint`:
   un campo nuevo en `ChunkingParameters` ya separa la caché.
7. Tests: `tests/chunking/domain/test_parameters.py` (valor por defecto, rechazo en un chunker que no lo usa, rango),
   `tests/chunking/adapters/data/test_chunking_mappers.py` (escribir → leer) y, si cambia el chunker,
   `tests/chunking/adapters/test_docling_chunkers.py` (marcador `docling`).
8. `http/chunking/experiments.http` y `config.http`, `CLAUDE.md` (las propiedades del `JSON`), la consola si el campo
   necesita un valor de ejemplo (`server/console/bodies.py`) y el pipeline si lo une con embeddings
   (`pipeline/domain/pairing.py`).

## docling-core

Chunking necesita solo el extra `chunk` (`docling-core[chunking]`: chunkers y tokenizadores, sin PyTorch ni los
modelos de layout de Docling). Sin él todo arranca, `GET /chunking/health` dice `docling_core: missing` y lo que
chunkea responde 503. Recordar que `uv sync` quita los extras que no se nombran:

```bash
uv sync --extra data --extra parse --extra chunk --extra embed
```

Actualizar docling-core cambia `docling_version`, que está en el fingerprint: todo queda faltante.

## Verificar

```bash
uv run ruff format && uv run ruff check && uv run mypy && uv run pytest
curl localhost:8000/chunking/health
curl localhost:8000/chunking/config                               # la configuración y su "fingerprint"
curl "localhost:8000/data/progress/chunking?fingerprint=<fingerprint>&per_page=1"   # cuántos faltan con ella
curl -XPOST localhost:8000/chunking/runs -H 'Content-Type: application/json' -d '{"simulate": true}'
# 200: sha256s (la lista) y progress: pending (se chunkearían), skipped (ya hechos), unparsed; no escribe nada
```
