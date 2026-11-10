# Cómo funciona la API

Un solo servidor HTTP (FastAPI + uvicorn) sirve los ocho módulos, cada uno bajo su prefijo. Los módulos también usan
esta API para hablar entre ellos: no se importan.

```bash
NEO4J_PASSWORD=... uv run prueba-chunking serve      # http://127.0.0.1:8000
# opciones: --host --port --base --ingest --memory --db --neo4j-url --neo4j-user --neo4j-database
#           --ollama-url (o OLLAMA_URL; por defecto http://127.0.0.1:11434)
#           --allowed-host (repetible) --max-body-bytes --log-level
uv run prueba-chunking ask "pregunta"                # POST /consultas/ask de un servidor que ya corre (--attach ARCHIVO: adjuntos)
NEO4J_PASSWORD=... uv run prueba-chunking migrate-vectors [--simulate]   # 055: una vez, con el servidor parado
```

`serve` no toca Docker: Neo4j y Ollama tienen que estar corriendo (la consola sí los levanta, con
`docker/compose.yaml`).

## Estructura del servidor

```
                         http://127.0.0.1:8000
              ┌────────────────────┴─────────────────────────────────┐
 GET /health  │ app raíz (src/server/app.py)                         │
 /processes   │  ├─ mount /ingesta    → memoria SQLite (por petición)  │──┐
 /processes/ws│  ├─ mount /data       → Neo4j (un adaptador para todo) │◄─┤  los módulos de trabajo
              │  ├─ mount /parsing    → Docling (extra parse)          │──┤  solo llaman a /data
              │  ├─ mount /chunking   → docling-core (extra chunk)     │──┤
              │  ├─ mount /embeddings → torch + transformers (embed)   │──┤
              │  ├─ mount /llm        → Ollama (--ollama-url)          │──┘
              │  ├─ mount /pipeline   → llama a todos los demás        │  consumidores: llaman
              │  └─ mount /consultas  → embeddings, data y llm         │  a otros módulos
              │  HostGuard (hosts servidos) · BodyLimit (32 MiB)       │
              └──────────────────────────────────────────────────────┘
```

- **Montar** (`app.mount`) en vez de `include_router` hace que cada módulo conserve su app: sus manejadores de error,
  su formato de error y su documentación (`/<módulo>/docs`).
- **`GET /health`** (raíz) consulta cada módulo en proceso y responde siempre 200, con `"status": "ok"` o
  `"degraded"` y el detalle por módulo. Cada módulo tiene además su `GET /<módulo>/health`, que dice qué le falta
  (Docling, docling-core, torch, Ollama, si `data` u otro módulo que llama responde).
- **`GET /processes`** y el WebSocket **`/processes/ws`**: los procesos de todos los módulos (corridas, experimentos,
  ingestas), vivos y terminados, con filtros `?phase&state`. Cada módulo tiene también el suyo.
- **Sin Neo4j** (falta la clave, el driver o la conexión), el servidor arranca igual: `/data` responde 503 en todo lo
  que toca el grafo y los módulos que dependen de él lo dicen en su `/health`. Si solo faltaba la conexión (Neo4j
  arrancando), `data` reintenta al usarse, como mucho cada 5 s (`ReconnectingGraph`, 054), y vuelve solo cuando Neo4j
  responde. Lo mismo con Ollama: `llm` abre un cliente por petición, así que responde 503 mientras Ollama no esté y
  funciona en cuanto vuelve.
- **Sin un extra**, su módulo arranca igual y responde 503 en lo que lo necesita.
- **Guardas** (feature 040): solo responde a los hosts de esta máquina, al de `self_url` y a los de `--allowed-host`;
  lee cuerpos de hasta `--max-body-bytes`. No hay autenticación: con `--host` no local, la CLI lo avisa.
- **Ciclo de vida:** el adaptador de Neo4j se abre una vez al arrancar y lo cierra el *lifespan* de la app raíz
  (Starlette no corre el de las sub-apps montadas).

## Errores

| Módulo | Cuerpo del error | Errores propios |
|---|---|---|
| ingesta | `{"detalle": "..."}` | memoria inaccesible → 503; error de disco → 500 |
| data | `{"detail": "..."}` | Neo4j caído o consulta rechazada → 503 |
| parsing | `{"detail": "..."}` | data no responde → 503; data rechaza → 502; sin Docling → 503; fila llena → 409 |
| chunking | `{"detail": "..."}` | data no responde → 503; data rechaza → 502; sin docling-core → 503; fila llena o sin configuración → 409 |
| embeddings | `{"detail": "..."}` | data o el modelo caídos → 503; data rechaza → 502; límite inválido → 422; sin torch → 503 |
| llm | `{"detail": "..."}` | Ollama caído o sin el modelo descargado → 503 (con el `ollama pull` que lo arregla); data caído → 503, la rechaza → 502; modelo no admitido, valor fuera de rango o imágenes sin visión → 422; fila de descargas llena → 409. Nunca un 500 por Ollama |
| pipeline | `{"detail": "..."}` | plantilla o petición inválida → 422; conflicto → 409; no existe → 404; un módulo no responde → 503, lo rechaza → 502 |
| consultas | `{"detail": "..."}` | embeddings, llm o data caídos → 503 (dice cuál); lo que llm o embeddings no admiten → 422; chat o experimento inexistente → 404; experimento sin terminar o chat del otro tipo → 409; data rechaza → 502 |

En todos, un cuerpo o parámetro inválido da **422** (los cuerpos rechazan claves desconocidas) y lo que no existe da
**404**. ingesta usa `detalle` en español porque esa clave ya estaba publicada antes de pasar el código al inglés.

## Trabajos en segundo plano

Ingestas, parseos, corridas y experimentos de chunking y de embeddings, y corridas del pipeline **corren en un hilo
propio**: la petición vuelve enseguida (202) con un `id` y el estado se consulta con `GET .../{id}` o en
`/processes`. Hacen peticiones HTTP al mismo servidor, que tiene que seguir libre para contestarlas.

- **Colas**: parsing, chunking y embeddings corren **uno a la vez** cada uno; lo que llega mientras otro corre queda
  `queued` en su fila (hasta `MAX_WAITING`, 100; llena, 409). `DELETE .../{id}` saca uno de la fila. ingesta corre
  una a la vez (otra → 409). Las descargas de modelos de `llm` también van de a una (fila de 20).
- **Sincrónico**: `POST /llm/chat` y `POST /consultas/ask` responden cuando el modelo termina (con timeout: 300 s por
  petición; `prueba-chunking ask` espera hasta 600 s).
- **Historial**: cada módulo guarda sus corridas (`corridas_api` en la memoria de ingesta; `CORRIDA_PARSEO`,
  `CORRIDA_CHUNKING`, `CORRIDA_EMBEDDINGS`, `EXPERIMENTO`, `EXP_EMBEDDINGS`, `PIPE_CORRIDA` en el grafo): los `GET`
  responden también las de antes de reiniciar, y lo que corría al apagarse queda `interrupted`.
- **`simulate`**: casi todo lo que lanza algo acepta `"simulate": true`, que solo cuenta qué haría, sin escribir.

## Rutas por módulo

### `/ingesta`: los archivos y sus estadísticas

| Método y ruta | Qué hace |
|---|---|
| `GET /health` | si la memoria se puede abrir |
| `GET /source` | la revisión del origen, que es **siempre la carpeta base del servidor** (`data/base/`): si existe, qué tiene, cuántos nuevos y sus `problemas` (no existe, vacío, sin estructura, solapa ingesta...) |
| `POST /runs` `{source?, simulate}` | corre la ingesta en segundo plano, **siempre copiando** (el origen queda intacto): copia lo nuevo, reclasifica y reubica, y al final **publica los aptos en data como `RAW`** (`resultado.en_data`: subidos, ya estaban, retirados, fallidos). 202; 200 con `simulate` (incluye `en_data`: cuántos subiría y retiraría); 422 con la revisión si el origen no sirve; 409 si ya hay una; 501 para `source.kind: sql` |
| `GET /runs[/{id}]` | estado (`en_curso`, `terminada`, `fallida`, `interrumpida`), progreso y resumen |
| `GET /data?type=&year=&month=&week=&code=&page=&per_page=` | los aptos para chunking, filtrados y paginados; `reorganizado` = fin de la última corrida |
| `GET /data/file?origin=` o `?sha256=` | el registro de un archivo apto (uno de los dos); 404 si no existe o no es apto |
| `GET /data/content?origin=` | el archivo mismo, con su `Content-Type`; nunca sale de `data/ingesta/` |
| `GET /stats` y `/stats/summary`, `/types[/{tipo}]`, `/years[/{anio}]`, `/duplicates`, `/empty`, `/codes`, `/repeated[/{anio}]`, `/cleanup` | las estadísticas de la memoria, completas o por sección |
| `GET /processes` | sus ingestas |
| `POST /uploads` (multipart: `files` o `files[]`, y `code`) | (049) guarda cada archivo en `data/base/<anio>/<MM_Mes>/Semana_NN/<code>/` de la fecha de subida (p. ej. `2026/11_Noviembre/Semana_02/023560/`), con el prefijo de fecha de los nombres del corpus, **sin pisar nada**. Responde una fila por archivo: `{nombre, estado, sha256, ruta, motivo}`, con `estado` `guardado`, `ya_existe` (el mismo sha256 ya está en el corpus o ya se subió; `ruta` dice dónde) o `rechazado` (`motivo`: solo pdf, doc y docx no vacíos, nombre válido). `code` de 6 dígitos (`000000` = sin PIAA). 413 si el cuerpo pasa el límite del servidor, 415 si no es multipart, 422 sin archivos, con un código inválido o un cuerpo mal formado. Una subida a la vez. **No ingesta**: después va `POST /pipeline/runs {"template": "produccion", "scope": "new"}` |
| `GET /uploads` | lo subido por la API (tabla `subidas` de la memoria), lo más nuevo primero |

El multipart se lee con la biblioteca estándar (`ingesta/api/multipart.py`): python-multipart, lo que necesita el
`UploadFile` de FastAPI, no es dependencia del proyecto. La consola muestra `POST /uploads` bloqueada: se sube desde la
API o el front (`http/ingesta/uploads.http`).

La memoria se abre y se cierra **en cada petición**: el convertidor de SQLAlchemy no se comparte entre hilos. Las
rutas de consulta nunca crean la memoria (si no existe, 503); solo `POST /runs` (en el hilo de su corrida) y `POST /uploads` la crean.

### `/data`: el grafo

| Método y ruta | Qué hace |
|---|---|
| `GET /health`, `GET /schema` | si Neo4j responde; etiquetas y relaciones permitidas |
| `GET/POST /nodes/{label}` | listar (paginado; `?omit=contenido` deja fuera propiedades pesadas; `?omit=embedding`, todos los vectores `embedding_<modelo>_<dim>`) / crear un nodo |
| `GET/PUT/PATCH/DELETE /nodes/{label}/{id}` | leer (`?omit=`) / reemplazar propiedades / cambiar solo las enviadas (`null` borra) / borrar con sus relaciones |
| `GET /nodes/{label}/{id}/relationships` | las relaciones que entran o salen del nodo |
| `POST /relationships`, `GET /relationships/{type}` | crear una relación (validada contra el esquema) / listar un tipo |
| `GET/PUT/PATCH/DELETE /relationships/{type}/{source_label}/{source_id}/{target_label}/{target_id}` | una relación concreta |
| `POST /batch` | muchos nodos y relaciones en **una transacción**, con modos `replace`/`ensure`/`merge` y `replace_from` (ver [guia-data.md](guia-data.md#reglas-del-grafo)); 422 sin escribir nada |
| `GET /progress/parsing?list=missing\|done&fingerprint=&page&per_page` | sobre los `RAW` vigentes: `total`, `done`, `missing`, `partial`, `errors`, `never` y una página de `sha256s`. Con `fingerprint` (el de `GET /parsing/config`), lo parseado con otra huella cuenta como faltante |
| `GET /progress/chunking?list=missing\|done&fingerprint=&page&per_page` | sobre los `JSON` parseados: lo mismo para el chunking oficial. Con `fingerprint` (el de `GET /chunking/config`), solo cuenta como hecho lo chunkeado con esa configuración sobre su parseo actual |
| `PUT/GET/DELETE /vectors/indexes/{name}` | crear con `{label, property, dimensions}` (si falta; uno con otra definición, 409) / ver / borrar un índice vectorial (coseno sobre una propiedad `embedding_<modelo>_<dim>` de `FRAGMENTOS` o `EXP_EMBED`; 055). `DELETE ...?drop_property=true` quita también esa propiedad de todos los nodos de la etiqueta (los vectores de ese modelo). El nombre (`vec_[a-z0-9_]+`), la propiedad y las dimensiones los pone `embeddings`; `data` valida el patrón antes de ponerla en Cypher |
| `POST /vectors/search` | `{index, vector, k, experiment?}` (`k` de 1 a 100): sin `experiment`, el índice debe ser de `FRAGMENTOS` y responde los de `JSON` chunkeados más cercanos; con `experiment` (048: el id de un experimento de embeddings), el índice debe ser de `EXP_EMBED` (055) y solo entran los vectores que calculó ese experimento; cada fila es su `EXP_CHUNK`. Cada fila: `{id, score, text, headings, pages, sha256, origin, code}` (`origin` y `code` del `RAW`). 404 si el índice no existe; 422 si es de la otra etiqueta o el vector tiene otras dimensiones |

### `/parsing`: de `RAW` a `DoclingDocument` (feature 042)

| Método y ruta | Qué hace |
|---|---|
| `GET /health` | Docling y el motor de OCR instalados, LibreOffice (solo para `.doc`, no degrada) y si data responde |
| `GET /config` | la configuración fija, su versión y la huella actual (`fingerprint`) |
| `POST /runs` `{sha256s, redo, simulate}` | parsea esos `sha256` (repetidos, una vez); sin `sha256s`, todos los `RAW` vigentes que faltan (con `redo`, todos). Lo ya parseado con la misma huella se salta (`redo` lo rehace) y un `parcial` se reanuda. Escribe `PIAA → JSON → RAW` en un lote por documento. 202 en la fila; 503 sin Docling |
| `GET /runs[/{id}]` | estado (`queued`, `running`, `finished`, `failed`, `interrupted`, `cancelled`) y el de cada documento (`parsed`, `partial`, `error`, `skipped`, `missing`) |
| `DELETE /runs/{id}` | saca de la fila una corrida que espera (queda `cancelled`) |
| `POST /preview` | (048 fase 2) un pdf, docx o doc con **la misma configuración fija**, respondido como texto: `{name, pages, truncated, text, sections: [{headings, text, pages}]}`. **No guarda nada** (no entra al corpus ni a data: eso es `POST /ingesta/uploads`). Cuerpo JSON `{name, content (base64), mime?}` o multipart con una parte `file`. De un PDF solo las primeras `PREVIEW_MAX_PAGES` (30) páginas (`truncated`); hasta `PREVIEW_MAX_BYTES` (20 MiB) y `PREVIEW_TIMEOUT` (180 s). Sincrónica y de a una, fuera de la fila de corridas: 409 si otra se está leyendo, 413, 415 otro tipo, 422 vacío o ilegible, 503 sin Docling, 504 pasado el tiempo. La usa `consultas` para los adjuntos |
| `GET /processes` | sus corridas |

Corridas y vistas previas comparten los convertidores de Docling y convierten **de a uno** (un lock en
`DoclingParser`): una vista previa espera a que termine el documento que esté convirtiendo una corrida.

Lo parseado no se lee por `parsing`: está en `data` (`GET /data/nodes/JSON/{sha256}?omit=documento`,
`GET /data/nodes/RAW/{sha256}?omit=contenido`).

### `/chunking`: corridas oficiales, experimentos y configuración (features 043 y 045)

| Método y ruta | Qué hace |
|---|---|
| `GET /health` | si docling-core está instalado y si data responde |
| `GET /config` | la configuración activa (y de dónde salió: `defecto`, `experimento`, `manual`), lo fijo, lo de por defecto, su huella (`fingerprint`) y, con `?documents=true` (lento), cuántos documentos oficiales están hechos con ella y con otra |
| `PUT/PATCH/DELETE /config` | ponerla a mano (lo que falta toma el valor por defecto) / cambiar solo lo enviado / volver a la de por defecto. No reprocesa nada |
| `POST /runs` `{sha256s}` o `{page, per_page}` o `{}`, `simulate` | **lo oficial**: chunkea con la configuración activa (leída al crear la corrida) esos documentos o, sin `sha256s`, lo que falta con ella (una página o todo, tomado cuando le toca el turno). Reemplaza lo que colgaba de cada `JSON` (`SECCION`/`FRAGMENTOS`). Lo ya hecho con la misma configuración sobre el mismo parseo se salta; uno sin parseo queda `sin_parseo`. `chunked` = lo que el pipeline le pasa a embeddings (los saltados también). 202 en la fila; 200 con `simulate`; 409 fila llena o sin configuración; 422 `sha256s` con `page`; 503 sin docling-core |
| `GET /runs[/{id}]` | estado (`queued`, `running`, `finished`, `partial`, `failed`, `interrupted`), progreso, `chunked` y fallos |
| `DELETE /runs/{id}` | saca de la fila una corrida que espera (queda `interrupted`, se puede retomar) |
| `POST /runs/{id}/resume` | retoma una `partial`, `failed` o `interrupted` con la misma lista y configuración: lo hecho se salta. 409 si la configuración activa cambió |
| `POST /experiments` `{name, description, sha256s \| from_experiment, chunking: {chunker, tokenizer, max_tokens, merge_peers}, simulate}` | chunkea esos documentos con esa configuración, aparte de lo oficial (`EXPERIMENTO`, `EXP_SECCION`, `EXP_CHUNK`). 202 en la fila; con `simulate`, 200 con cuáles entrarían y cuáles no están parseados; 409 si la fila está llena o ninguno está parseado |
| `GET /experiments[/{id}]`, `DELETE /experiments/{id}` | listar (también los de antes de reiniciar) / ver (petición, progreso, `chunked`, resultados de tokens y chunks) / borrar con sus secciones y chunks (los `JSON` quedan) |
| `POST /experiments/{id}/apply` | copia su configuración a la activa; 409 si no está `finished`. No chunkea nada: eso es `POST /runs` |
| `POST /experiments/{id}/resume` | chunkea, con su propia configuración, los documentos que no alcanzó o que fallaron |
| `GET /processes` | corridas y experimentos |

Los chunks no se leen por `chunking`: están en `data` (`SECCION`/`FRAGMENTOS` bajo un `JSON`, `EXP_SECCION`/`EXP_CHUNK`
de un experimento).

### `/embeddings`: vectores (features 046 y 055)

Único módulo que calcula vectores; solo habla con `data`. Recibe listas explícitas (el pipeline elige qué).

| Método y ruta | Qué hace |
|---|---|
| `GET /health`, `GET /models` | si `torch`/`transformers` están (sin cargar el modelo) y data responde / los modelos con dimensiones, `default_tokens`, `max_tokens` (cuentan los 2 tokens especiales), `default` y `documents` (con `?documents=true`, 055: cuántos documentos oficiales tienen sus vectores; lee todos los `JSON`, lento) |
| `DELETE /models/{name}/vectors` | (055) quita los vectores oficiales de ese modelo: su huella de cada `JSON`, su índice de `FRAGMENTOS` y su propiedad. 409 si es el modelo activo; los `EXP_EMBED` de los experimentos quedan |
| `GET/PUT/PATCH/DELETE /config` | la configuración activa (modelo y `max_tokens`, `CONFIG_OFICIAL/embeddings`); 422 si el modelo no está o el límite no cabe |
| `POST /runs` `{sha256s, force, simulate, model?}` | embebe los `FRAGMENTOS` de esos `JSON` chunkeados con la configuración activa (o con `model`, otro servido, **al lado** del activo: 055) en `embedding_<modelo>_<dim>`; salta lo que no cambió (`huella_embedding_<modelo>_<dim>`); un chunk más largo que el límite falla su documento. 202 en la fila, 200 con `simulate`, 409 fila llena |
| `GET /runs[/{id}]`, `DELETE /runs/{id}` | estado, avance, fallos y `embedded` (lo que el pipeline lee) / sacar de la fila |
| `POST /experiments` `{name, description, chunking_experiment, model, max_tokens, simulate}` | embebe los `EXP_CHUNK` de un experimento de chunking terminado (404 si no existe, 409 si no terminó): un `EXP_EMBED` por chunk con el vector (055) |
| `GET /experiments[/{id}]`, `DELETE /experiments/{id}`, `POST /experiments/{id}/apply` | listar / ver / borrar (con los vectores que dejó) / copiar su modelo y límite a la activa |
| `POST /vectors` `{texts, model?, max_tokens?}` | (048) hasta 64 textos → sus vectores, en orden, con el modelo activo (o con `model`, otro servido, como el de un experimento). Un texto más largo que el límite se corta (es una pregunta, no un documento). Responde `{model, max_tokens, dimensions, index, experiment_index, vectors}`: `index` y `experiment_index` son los nombres de los índices de `FRAGMENTOS` y `EXP_EMBED` de ese modelo (con e5, la pregunta lleva su prefijo `query: `). 422 si el modelo o el límite no sirven; 503 sin torch. `POST /search` se quitó: la búsqueda es de `consultas` |
| `GET /processes` | corridas y experimentos |

**Cambiar de modelo sin cortar el chat** (055): `POST /runs {sha256s, model: "<nuevo>"}` (los vectores del nuevo quedan al
lado de los del activo) → `PUT /config {model: "<nuevo>"}` (el chat pasa a buscar en su índice) →
`DELETE /models/<viejo>/vectors`. Candidatos además del MiniLM: `intfloat/multilingual-e5-base` (768, prefijos
`query: `/`passage: `) y `BAAI/bge-m3` (1024, pooling CLS). Los vectores guardados antes de la 055 se mueven una vez con
`prueba-chunking migrate-vectors [--simulate]`, con el servidor parado.

### `/llm`: los modelos de lenguaje, por Ollama (feature 047)

Único módulo que habla con Ollama; solo habla además con `data` (su configuración). No sabe de documentos.

| Método y ruta | Qué hace |
|---|---|
| `GET /health` | si Ollama responde (`ollama`, `ollama_version`, `ollama_url`) y si data responde; siempre 200 |
| `GET /models` | `{admitted: [{name, context, vision, installed, default}], installed: [{name, size, family, modified}]}`: los que admite el proyecto (`qwen2.5:0.5b`, `llama3.1:8b` —por defecto—, `qwen2.5vl:3b` —visión—) y todo lo que Ollama tiene. 503 si Ollama no responde |
| `POST /models/pull` `{name}` | baja un modelo admitido en segundo plano, de a uno (los demás `queued`): 202 con la descarga (`id`, `model`, `status`, `step`, `completed`, `total`...). 422 si no es admitido; 409 fila llena; 503 sin Ollama |
| `GET /models/pulls[/{id}]` | las descargas de esta sesión (solo en memoria), la más nueva primero / una (`queued`, `running`, `finished`, `failed`) |
| `DELETE /models/{name}` | lo quita de Ollama; 409 si es el de la configuración activa, 404 si Ollama no lo tiene |
| `GET/PUT/PATCH/DELETE /config` | la configuración activa (`CONFIG_OFICIAL/llm`): `{model, temperature, num_ctx, max_tokens, system, origin, modified, default}`. `PUT {model, ...}`: lo que falta toma el valor por defecto (`num_ctx`, el del modelo); `PATCH`: solo lo enviado (otro modelo conserva `num_ctx` si cabe); `DELETE`: vuelve a la de por defecto. 422 si no cabe |
| `POST /chat` | `{messages: [{role: system\|user\|assistant, content, images?: [base64]}], model?, temperature?, num_ctx?, max_tokens?}` → `{model, message: {role: "assistant", content}, prompt_tokens, answer_tokens, seconds}`. Lo que no se envía sale de la configuración activa, y su `system` va primero si los mensajes no traen uno. Sincrónico, sin streaming. 422 si el modelo no es admitido, un valor está fuera de rango o hay imágenes con un modelo sin visión; 503 si Ollama no responde o no tiene el modelo |
| `GET /processes` | las descargas |

### `/pipeline`: plantillas, corridas y actores (features 028 y 044)

| Método y ruta | Qué hace |
|---|---|
| `GET /health` | si responde cada módulo que llama (ingesta, parsing, chunking, embeddings, llm, data) |
| `GET /actions` | el catálogo de acciones, con `needs`, `gives`, módulo y parámetros |
| `GET/POST /pipelines`, `POST /pipelines/check` | listar / crear una plantilla / revisar un orden de etapas sin guardarlo (422 con la etapa a la que le falta algo) |
| `GET/PUT/DELETE /pipelines/{id}` | una plantilla (`produccion` y `laboratorio` se pueden cambiar, no borrar) |
| `PUT /pipelines/{id}/stages`, `POST /pipelines/{id}/stages/{stage}/move` | reordenar todas / mover una (`before`/`after`) |
| `POST /runs` `{template, name, files, params, scope, simulate}` | lanza una corrida. `produccion`: `scope` `new` (lo recién parseado) o `all` (todo lo parseado). `laboratorio`: `files` = `{all \| pages: {from, to} + per_page \| sha256s \| from_run}` con filtros `types/year/month/week/code`, y `params` del ciclo (`{"chunking": {...}, "embeddings": {"model"}, "llm": {model, temperature, num_ctx, max_tokens, system}}`: el par se valida contra `GET /embeddings/models` y `llm` —opcional, 050— contra `GET /llm/models`, admitido y descargado; 422 si no cuadran) |
| `GET /runs[/{id}]` | corridas (`queued`, `running`, `waiting`, `done`, `failed`, `cancelled`, `interrupted`) con el registro de cada etapa y sus artefactos; cada iteración con su `llm` y, si reutiliza los experimentos de otra, `reused` |
| `POST /runs/{id}/stages/{stage}/decision` | el actor de un ciclo: `{"decision": "retry", "next": {...}, "score": {...}}` o `{"decision": "approve", "iteration": n}`; 409 si la etapa no espera a ese actor. Un `next` con solo `llm` reutiliza los experimentos de chunking y embeddings de la iteración (050). Aprobar aplica el trío: `aplicar_chunking`, `aplicar_embeddings` y `aplicar_llm` (`PUT /llm/config`; sin `llm` en el ciclo no hace nada) |
| `POST /runs/{id}/stages/{stage}/complete` | el actor de una etapa `external`: `{actor, result}` o `{actor, error}` |
| `POST /runs/{id}/events`, `/resume`, `/cancel` | un evento del actor / retomar una `failed` o `interrupted` / cancelar |
| `GET /inbox?actor=` | lo que espera a cada actor, con la ruta para responder: `experiment`, `embeddings_experiment` y `llm` de la iteración (lo que `lab` evalúa con `POST /consultas/ask {against: {embeddings_experiment}, llm}`), `batch` y `artifacts` |
| `GET /actors`, `PUT /actors/{name}` | los actores y su `callback_url` (solo hosts de esta máquina o de `PIPELINE_CALLBACK_HOSTS`; hoy en memoria) |
| `GET /processes` | sus corridas |

### `/consultas`: el RAG (feature 048)

Un consumidor, como el pipeline: llama a `embeddings`, `data` y `llm` (y a `parsing`, solo para los documentos adjuntos). No corre trabajos (no tiene `/processes`).

| Método y ruta | Qué hace |
|---|---|
| `GET /health` | si embeddings, llm, data y parsing responden; siempre 200 (`degraded` si alguno de los tres primeros no; sin parsing solo no se adjuntan documentos) |
| `POST /search` `{question, k?, against?: {embeddings_experiment}, attachments?}` | los fragmentos más parecidos, sin LLM ni `min_score`, el mejor primero: `[{id, score, text, headings, pages, sha256, origin, code}]`. La pregunta se vectoriza con el modelo activo de embeddings y se busca en su índice; con `against`, en los `EXP_CHUNK` de ese experimento de embeddings (con su modelo). Lista vacía si nada se embebió con ese modelo. Con `attachments`, también buscan los adjuntos (ver abajo) |
| `POST /ask` `{question, k?, chat?, llm?: {model, temperature, num_ctx, max_tokens}, against?, attachments?}` | → `{answer, sources, chat, consulta, model, found, seconds: {search, answer}, laboratory, attachments}`. Busca, se queda con los que pasan `min_score` (numerados como los cita la respuesta: `[1]`...) y le pide la respuesta a `llm`; si ninguno pasa, responde que no encontró información, `found: false`, `model: null`, y no llama al LLM. Sin `chat` abre uno nuevo (titulado con el comienzo de la pregunta); con él, sus últimos `history` turnos van al LLM. `llm` cambia el modelo o la temperatura solo para esa pregunta. Con `against`, la consulta y su chat quedan `laboratorio` (409 si se sigue un chat del otro tipo; 404/409 si el experimento no existe o no terminó). La pregunta, la respuesta y sus citas se guardan en un lote: todo o nada |
| `GET /chats`, `GET /chats/{id}` | los chats, el modificado más reciente primero / uno con sus consultas, la más vieja primero, cada una con su respuesta y los fragmentos que citó |
| `DELETE /chats/{id}` | el chat y sus consultas (por `GENERA`, composición); los fragmentos citados quedan |
| `GET/PUT/PATCH/DELETE /config` | la configuración activa (`CONFIG_OFICIAL/consultas`): `{k, min_score, prompt, history, origin, modified, problem, default}`. Por defecto `k` 5 (máx. 50), `min_score` 0.3, `history` 3 (máx. 20) y un prompt en español que exige citar; `prompt` debe tener `{context}` y `{question}` (422 si no) |

**Adjuntos** (fase 2): `attachments: [{name, content (base64), mime?}]` (sin `mime`, por la extensión; con adjuntos
`question` puede faltar). Un documento (pdf, docx, doc) se lee con `POST /parsing/preview`, se corta en trozos del
tamaño del modelo de embeddings y cada trozo busca; una imagen (png, jpg, webp) la describe un modelo de visión de
`llm` (`VISION_MODEL` `qwen2.5vl:3b` o, si no está descargado, otro de visión que tenga; ninguno → 503 con cómo
bajarlo) y su descripción busca. Las búsquedas se unen por el mejor puntaje de cada fragmento. Límites:
`MAX_ATTACHMENTS` 4 por pregunta, `MAX_ATTACHMENTS_BYTES` 20 MiB entre todos, `MAX_PIECES` 48 trozos (un documento
más largo se muestrea); fuera de eso, 422. `attachments` de la respuesta dice qué buscó cada uno (`pieces`,
`characters`, `truncated`, `description` de una imagen). Nada de los adjuntos se guarda: la `CONSULTA` anota solo
`adjuntos` (nombres), `tipos_adjuntos` y `caracteres_busqueda`. Desde la terminal: `prueba-chunking ask --attach ARCHIVO`.

Lo guardado (contratos en [`048-consultas-rag/contratos.md`](../spec/features/048-consultas-rag/contratos.md)):
`CHAT {titulo, creado_en, modificado_en, laboratorio}`, `CONSULTA {pregunta, respuesta, modelo_llm, modelo_embedding, k,
creado_en, segundos, laboratorio, experimento_embedding, encontrada}` y
`(:CHAT)-[:GENERA]->(:CONSULTA)-[:RESPONDIDA_CON {puntaje, orden}]->(:FRAGMENTOS | :EXP_CHUNK)`.

## Cómo se hablan los módulos

Los módulos no se importan: usan la misma API pública que cualquier cliente externo, contra
`ServerSettings.self_url` (por defecto `http://127.0.0.1:<puerto>`).

```
ingesta     ── GET /data/nodes/RAW?omit=contenido · POST /data/batch (un RAW por lote) ──────────────►┐
parsing     ── GET /data/nodes/RAW/{sha256} · POST /data/batch (PIAA → JSON → RAW) · CORRIDA_PARSEO ─►│
chunking    ── GET /data/nodes/JSON/{sha256} · GET /data/progress/chunking · POST /data/batch ───────►│ data
embeddings  ── GET /data/nodes/... (?omit=embedding) · POST /data/batch · PUT/DELETE /data/vectors/indexes►│
llm         ── GET/POST /data/nodes/CONFIG_OFICIAL/llm (su configuración); Ollama: /api/chat, /api/tags…►│
pipeline    ── todo lo anterior por la API de cada módulo: POST .../runs, GET .../runs/{id} ──────────►┘
               (y GET /ingesta/data para elegir un lote; GET /data/nodes/JSON para scope all;
                GET /llm/models y PUT /llm/config para el llm del laboratorio)
consultas   ── POST /embeddings/vectors · GET /embeddings/experiments/{id} · POST /data/vectors/search
               · POST /llm/chat · POST /data/batch (CHAT → CONSULTA → fragmentos) · GET /data/nodes/CHAT…
               · con adjuntos: POST /parsing/preview y GET /llm/models (el modelo de visión)
```

- **Regla**: los módulos de trabajo (`ingesta`, `parsing`, `chunking`, `embeddings`, `llm`) solo nombran rutas de
  `/data` (`tests/common/test_module_rule.py`). Solo los consumidores (`pipeline` y `consultas`) llaman a los demás.
- **Errores entre módulos**: el cliente base común (`common/http/base_client.py`, el único que llama a `httpx`)
  traduce red caída, timeout, 5xx o una respuesta que no es JSON al error «no disponible» del módulo (corta el
  trabajo), un 404 a `None` o al error que pida la llamada, y otro 4xx a «rechazado» (en general, falla solo ese
  documento).
- **Esperar a otro módulo**: el pipeline lanza (`POST`), reintenta si la fila está llena (409, cada `BUSY_RETRY`) y
  sondea `GET .../{id}` hasta que el estado deja de ser `queued`/`running` (`pipeline/adapters/http/jobs.py`).
- **Dónde está el código**: un cliente delgado por recurso en `adapters/` de cada módulo, sus **mappers** (el único
  lugar donde los nombres guardados en español se vuelven modelos) y las fachadas que implementan los puertos.

## Agregar una ruta

1. **Spec** de la feature con la ruta, su cuerpo, sus respuestas y sus errores.
2. **Esquemas** en `api/schemas.py` del módulo (o `api/<recurso>/schemas.py`): dataclasses congeladas para el cuerpo
   (con `STRICT`, que rechaza claves desconocidas) y la respuesta. En ingesta las claves JSON van en español; en los
   demás, en inglés.
3. **Ruta** en `api/routes/<recurso>.py`: un `APIRouter` por archivo, sumado a `ROUTERS` en `api/routes/__init__.py`.
   La ruta solo traduce: recibe las dependencias, llama al dominio o al store, y convierte los errores en
   `HTTPException` con el formato del módulo.
4. **Orden:** una ruta fija va **antes** que una con parámetro del mismo tramo, o FastAPI toma el texto como id.
5. **Documentar las respuestas** de error en el decorador (`responses={404: …, 503: …}`) para que salgan en `/docs`.
6. **Si otro módulo la consume:** solo un consumidor (el pipeline o `consultas`) puede; su cliente va en su
   `adapters/`.
7. **Probarla:** test en `tests/<módulo>/api/`, las peticiones en el archivo de `http/` que corresponda y, si es un
   camino entre módulos, en `http/connections/`. La consola la muestra sola (ver [guia-consola.md](guia-consola.md)).

## Probar con los archivos `http/`

`http/` tiene peticiones listas para la extensión REST Client de VS Code («Send Request» sobre cada una). Hay un archivo
por grupo de rutas:

| Carpeta o archivo | Qué prueba |
|---|---|
| `server.http` | `/health` y los `/docs` |
| `ingesta/` | `health`, `data` (lista, archivo, contenido), `stats`, `runs` (revisión del origen y corridas), `uploads` (subir y listar), `processes` |
| `data/` | `health`, `nodes`, `relationships`, `batch` (cada uno crea sus datos de prueba y los borra; no correr `nodes` y `relationships` a la vez, comparten ids), `progress`, `vectors` |
| `parsing/` | `info` (health y config), `runs`, `preview` (leer un documento sin guardar) |
| `chunking/` | `health`, `config`, `runs`, `experiments`, `processes` |
| `embeddings/` | `info` (health, modelos, config), `runs`, `experiments`, `vectors` (texto → vector) |
| `llm/` | `info` (health, config), `models` (modelos y descargas), `chat` |
| `pipeline/` | `pipelines`, `produccion`, `laboratorio` (con el trío chunking + embeddings + llm), `inbox` |
| `consultas/` | `questions` (health, search, ask), `chats` (chats y configuración) |
| `connections/` | caminos entre módulos de punta a punta: `health`, `ingesta-data`, `chunking-data`, `embeddings-data`, `pipeline`, `consultas` |

- **Peticiones encadenadas:** varias usan la respuesta de una anterior (`# @name`, `{{nombre.response.body.$.campo}}`).
  Se ejecutan de arriba a abajo. Es sintaxis de REST Client.
- **Datos reales:** las que escriben en el grafo con ids de prueba (`test-*`) limpian al final. Las corridas de
  parsing, chunking y embeddings que no son `simulate` escriben sobre documentos reales, con sus ids definitivos, y
  cada `POST /consultas/ask` guarda un chat de verdad.
- **Otro puerto:** cambiar la variable del principio de cada archivo.

Neo4j de prueba, sin tocar el real:

```bash
docker run -d --rm --name neo4j-prueba -p 17687:7687 -e NEO4J_AUTH=neo4j/clave-prueba neo4j:2026.07.1
NEO4J_PASSWORD=clave-prueba uv run prueba-chunking serve --neo4j-url neo4j://localhost:17687 --port 18000 \
    --memory /tmp/copia.sqlite3
```

La documentación interactiva de cada módulo, con todos los esquemas, está en `http://127.0.0.1:8000/<módulo>/docs`.
