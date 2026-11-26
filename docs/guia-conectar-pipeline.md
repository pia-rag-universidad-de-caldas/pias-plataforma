# Guía: conectar un módulo al pipeline

El pipeline (`src/pipeline/`, features 028, 044 y 050) corre **plantillas**: etapas en orden, cada una con una **acción**. Una
acción declara qué artefactos necesita (`needs`) y cuáles da (`gives`), y `Order.check` rechaza con 422 un orden en que
a una etapa le falta algo. Hay dos formas de que un módulo participe:

| | A. Actor externo | B. Tarea automática |
|---|---|---|
| Quién hace el trabajo | un proceso que no es del pipeline (otro servicio, una persona, un script) | el pipeline, llamando por HTTP a un módulo de `src/` |
| Código en el pipeline | **ninguno** | un puerto, un cliente, una acción, una cola |
| Cómo se entera | `GET /pipeline/inbox?actor=...` o un aviso POST a su `callback_url` | — |
| Cómo responde | `POST /pipeline/runs/{id}/stages/{etapa}/complete` | lo que devuelve su acción |
| Ejemplos hoy | `lab` (el ciclo del `laboratorio`) | `ingesta.run`, `parsing.parse_all`, `chunking.promote`, `embeddings.embed`, `llm.apply` |

Si el módulo hace un trabajo largo o vive fuera del servidor, empezar por **A**: no toca código y se puede pasar a B
después.

## A. Como actor externo (sin código)

### 1. Ponerlo en la plantilla

Una etapa con la acción `external`, su `actor` y lo que necesita y da (nombres de artefactos):

```json
{"id": "indexar", "action": "external", "actor": "indexador", "needs": ["embebidos"], "gives": ["indice"]}
```

Claves admitidas de una etapa: `id`, `action`, `params`, `actor`, `stages`, `max_iterations`, `needs`, `gives`.
`needs` tiene que darlo una etapa anterior (si no, 422 con el nombre de la etapa). Los artefactos que ya existen están
en `src/pipeline/models/concepts.py` (`FILE_BATCH = "lote_archivos"`, `RAW_FILES = "archivos_raw"`,
`PARSED = "parseados"`, `CHUNKED = "chunkeados"`, `EMBEDDED = "embebidos"`, `CHUNKING_EXPERIMENT`,
`EMBEDDINGS_EXPERIMENT`, `APPROVED_*`, y de la 050 `APPROVED_LLM = "llm_aprobado"` (el `llm` de la iteración
aprobada, si tenía) y `LLM_APPLIED = "configuracion_llm"`...; `GET /pipeline/actions` los lista por acción).

Para agregarla:

```bash
curl localhost:8000/pipeline/pipelines/produccion                 # las etapas actuales
curl -XPUT localhost:8000/pipeline/pipelines/produccion -H 'Content-Type: application/json' \
  -d '{"stages": [ ...las de antes..., {"id": "indexar", "action": "external", "actor": "indexador",
       "needs": ["embebidos"], "gives": ["indice"]}]}'
# antes de guardar, revisar el orden: POST /pipeline/pipelines/check {"stages": [...]}
# o una plantilla nueva: POST /pipeline/pipelines {"id": "con-indice", "stages": [...]}
# reordenar: PUT /pipeline/pipelines/{id}/stages {"order": [...]}  o  POST .../stages/{etapa}/move {"after": "..."}
```

`produccion` y `laboratorio` son las plantillas incorporadas (`domain/templates.py`): se pueden modificar por la API
pero no borrar. Para que **siempre** traigan la etapa nueva, agregarla en `domain/templates.py` (y su test en
`tests/pipeline/domain/test_order.py`: `test_the_builtin_templates_are_valid`).

### 2. Registrar el actor (si quiere aviso)

```bash
curl -XPUT localhost:8000/pipeline/actors/indexador -H 'Content-Type: application/json' \
  -d '{"callback_url": "http://mi-servicio/avisos"}'
```

La URL debe ser `http` o `https` y su host, de esta máquina o de la variable `PIPELINE_CALLBACK_HOSTS` del servidor
(separados por comas; para este ejemplo, `PIPELINE_CALLBACK_HOSTS=mi-servicio`); si no, responde 422. Las direcciones
de enlace local, de metadatos de nube, multicast y sin especificar se rechazan siempre, también si están en la lista.
Al avisar se vuelve a revisar el destino y no se siguen redirecciones.

Sin `callback_url` igual funciona: el actor consulta su bandeja. Ojo: hoy los actores viven en memoria
(`api/actor_registry.py`) y se pierden al reiniciar el servidor; los conocidos al arrancar están en
`config.ACTORS` (hoy solo `lab`).

### 3. Lo que recibe

Cuando una corrida llega a su etapa, queda `waiting`; el actor la ve en `GET /pipeline/inbox?actor=indexador` y, si
tiene `callback_url`, recibe un POST (sin reintentos; si falla, queda un evento `notify_failed` en la corrida y la
etapa sigue en la bandeja) con:

```json
{"run": "...", "name": "...", "stage": "indexar", "step": "indexar", "actor": "indexador", "since": "...",
 "iteration": null, "exhausted": false, "experiment": null, "embeddings_experiment": null, "llm": null,
 "batch": ["sha256", "..."], "artifacts": {"embebidos": ["..."]},
 "answer": "/pipeline/runs/<id>/stages/indexar/complete"}
```

En un ciclo del `laboratorio`, `experiment` y `embeddings_experiment` son los experimentos de la iteración y `llm`
su configuración del LLM (050: `{model, temperature, num_ctx, max_tokens, system}`, o `null` si el ciclo no trae):
`lab` evalúa la iteración con `POST /consultas/ask {"question": ..., "against": {"embeddings_experiment": ...},
"llm": ...}`.

### 4. Cómo responde

```bash
curl -XPOST localhost:8000/pipeline/runs/<id>/stages/indexar/complete -H 'Content-Type: application/json' \
  -d '{"actor": "indexador", "result": {"vectores": 1200}}'          # su resultado llena cada artefacto de `gives`
# si falló: {"actor": "indexador", "error": "sin espacio"}  → la corrida queda failed; POST .../resume la reintenta
```

409 si la corrida no está esperando a ese actor en esa etapa.

### Si su trabajo se repite hasta que alguien aprueba

Eso es un **ciclo**: una etapa con `"action": "cycle"`, su `actor` (quien aprueba), `stages` (la última, y solo esa,
`review.score`) y `max_iterations` opcional. El actor del ciclo responde en
`POST .../stages/{ciclo}/decision` con `{"decision": "retry", "next": {...}, "score": {...}}` (`next` se fusiona con
la configuración de la iteración anterior; `score` queda en la iteración) o `{"decision": "approve"}` (por defecto
aprueba la última; `"iteration": n` elige otra). Lo que da un ciclo aprobado es la versión aprobada de lo que dan sus
etapas. Ver el ciclo `laboratorio` en `domain/templates.py`: desde la 050 su `next` puede traer `llm`, y un `next` con
**solo** `llm` reutiliza los experimentos de chunking y embeddings de la iteración anterior
(`PIPE_ITERACION.reutiliza`; `engine._reusing`/`_skip_reused` registran esas etapas como reutilizadas en vez de
correrlas).

## B. Como tarea automática (un módulo de `src/`)

El pipeline nunca importa a otro módulo: lo llama por HTTP. El ejemplo conecta un módulo **`indice`** montado en
`/indice` que expone `POST /indice/builds` (si el módulo aún no existe, ver [guia-nuevo-modulo.md](guia-nuevo-modulo.md)).

**El caso real más reciente es `llm` (feature 050)**, que sigue exactamente estos pasos: `LlmPort` (`models`,
`apply`) en `models/ports.py` y su campo `llm` en `Modules`; `adapters/llm_client.py` (`LlmClient`: `GET /llm/models`,
`PUT /llm/config`, sobre `BaseHttpClient` porque no lanza trabajos); `LLM_MODELS`/`LLM_CONFIG` en `config/settings.py`
y `LLM_PATH` de `common.config`; `llm_path` en `ApiSettings`, `HttpModules` y `/pipeline/health`; `"llm"` en `QUEUES`;
la acción `domain/actions/llm.py` (`LlmApply`, `llm.apply`: `needs` el experimento de embeddings aprobado, `gives`
`configuracion_llm`, y lee `llm_aprobado`; si no está, no hace nada); la etapa `aplicar_llm` en la plantilla
`laboratorio`; y la validación previa en `domain/pairing.py` (`fit_llm`, contra `LlmPort.models()`). Los tests:
`tests/pipeline/adapters/test_pipeline_llm_client.py`, `tests/pipeline/domain/test_engine_llm.py` y los de `Order`,
`pairing` y el ejecutor.

### 1. El puerto (`src/pipeline/models/ports.py`)

Lo que el pipeline necesita del módulo, sin HTTP:

```python
class IndicePort(ABC):
    @abstractmethod
    def build(self, sha256s: tuple[str, ...]) -> str:
        """Builds the index of those documents and returns its id; UnavailableError/RejectedError if it can't."""
```

y el campo en `Modules`:

```python
@dataclass(frozen=True)
class Modules:
    ingesta: IngestaPort
    parsing: ParsingPort
    chunking: ChunkingPort
    embeddings: EmbeddingsPort
    data: DataPort
    llm: LlmPort
    indice: IndicePort
```

Exportar `IndicePort` en `models/__init__.py`.

### 2. El cliente (`src/pipeline/adapters/indice_client.py`)

Con el cliente base común y la política de errores del pipeline (`errors`): red, 5xx o una respuesta que no es JSON →
`UnavailableError` (503); otro 4xx → `RejectedError` (502).

```python
"""indice over HTTP (feature NNN)."""

import httpx

from pipeline.models import IndicePort, UnavailableError

from .http import BaseHttpClient, errors


class IndiceClient(BaseHttpClient, IndicePort):
    def __init__(self, client: httpx.Client, path: str) -> None:
        super().__init__(client, path, errors("indice"))

    def build(self, sha256s: tuple[str, ...]) -> str:
        response = self._request("POST", "/builds", body={"sha256s": list(sha256s)})
        body = self._object(None if response is None else self._json(response), "build")
        id = body.get("id")
        if not isinstance(id, str):
            raise UnavailableError(f"indice answered a build without id: {body!r}")
        return id
```

Si el módulo lanza un trabajo en segundo plano (`202` con un `id` y `GET .../{id}` para seguirlo), heredar de
`JobClient` (`adapters/http/jobs.py`) en vez de `BaseHttpClient`: espera los 409 de una fila llena (cada `BUSY_RETRY`)
y sondea el estado hasta que deja de ser `queued`/`running` (ver `ChunkingClient.promote` o `ParsingClient`). Si la
respuesta tiene muchos campos, su lectura va en `adapters/mappers.py`.

**Cancelar (056).** Cada método del puerto que lanza un trabajo recibe un `watch: JobWatch | None` (de
`ActionContext.watch`) y se lo pasa a `self._job(route, body, watch, stoppable=...)`. Con él, una corrida del pipeline
ya cancelada no lanza nada (tampoco tras un 409) y, si el módulo tiene `POST {route}/{id}/cancel` (`stoppable=True`:
hoy las corridas de parsing, chunking y embeddings), `POST /pipeline/runs/{id}/cancel` le pide cortar su trabajo al
terminar el documento actual; el cliente sigue esperando a que termine y el ejecutor descarta el resultado. Un módulo
sin esa ruta (ingesta, los experimentos) se espera hasta el final. Si el módulo nuevo procesa documento por
documento, conviene darle esa ruta: su dominio recibe un `stop: Callable[[], bool]` que mira antes de cada documento,
el registro guarda `cancel_requested` y la corrida termina conservando lo hecho.

### 3. Dónde está (`config`, sesión, servidor)

- `src/pipeline/config/settings.py`: `INDICE_PATH = "/indice"` (y en `config/__init__.py`).
- `src/pipeline/api/dependencies.py`: `indice_path: str = INDICE_PATH` en `ApiSettings`.
- `src/pipeline/adapters/session.py`: el parámetro en `HttpModules` y `IndiceClient(self._client, indice_path)` dentro
  de `Modules(...)`.
- `src/pipeline/api/app.py`: pasar `settings.indice_path` a `HttpModules`.
- `src/pipeline/api/routes/health.py`: `"indice": settings.indice_path` en `paths`, para que `GET /pipeline/health`
  diga si responde.
- `src/server/app.py`: hoy arma `PipelineSettings(settings.self_url, INGESTA, CHUNKING, DATA, PIPELINE)` y deja
  `parsing_path`/`embeddings_path`/`llm_path` por defecto; para el nuevo, pasarlo por nombre: `..., indice_path=INDICE)`.

### 4. La cola (`src/pipeline/api/executor.py`)

Cada acción corre en la cola de su `module`: un trabajador por cola, en orden de llegada. **Sumar `"indice"` a
`QUEUES`**; si no, la tarea falla al encolarse (`KeyError` en `Executor._continue`) y la corrida no avanza.

```python
QUEUES = ("ingesta", "parsing", "chunking", "embeddings", "data", "llm", "indice")
```

### 5. La acción (`src/pipeline/domain/actions/indice.py`)

```python
"""Building the index of the embedded documents (feature NNN)."""

from pipeline.models import EMBEDDED, Action, ActionContext, ActionError, ActionOutput, StageKind

INDEX = "indice"  # the artifact it gives (better: a constant in models/concepts.py, next to the others)


class IndiceBuild(Action):
    name = "indice.build"
    kind = StageKind.TASK
    module = "indice"  # its queue
    needs = (EMBEDDED,)
    gives = (INDEX,)
    description = "builds the index of the embedded documents"
    parameters = "none"  # what it reads from its configuration (shown in GET /pipeline/actions)

    def run(self, context: ActionContext) -> ActionOutput:
        sha256s = context.artifacts.get(EMBEDDED)
        if not isinstance(sha256s, list) or not sha256s:
            raise ActionError(f"{context.stage.id}: there are no embedded documents")
        id = context.modules.indice.build(tuple(str(s) for s in sha256s))
        return ActionOutput({INDEX: id}, {"index": id})
```

- Una acción que trabaja sobre una lista de documentos de un lote puede ir **por partes** (056): si su nombre está en
  `PART_ACTIONS` (`domain/parts.py`) y queda junto a `chunking.promote`, entra al bloque que una corrida con
  `part_size` (o con `files` y sin `ingesta.chunkable`) recorre una vez por parte. Dentro de una parte,
  `context.part` dice cuál y `context.artifacts[FILE_BATCH]` son sus sha256; lo que la acción da para una parte se
  suma al de la corrida al terminar la parte.
- `context.config` es la configuración de la etapa (sus `params`, los de la corrida para esa etapa y, en un ciclo, los
  de la iteración); `context.artifacts`, lo que dieron las etapas anteriores.
- Un error esperado es `ActionError` (la corrida queda `failed`, se reintenta con `resume`); `UnavailableError` y
  `RejectedError` del cliente también fallan la etapa.
- Sin HTTP aquí: solo el puerto (`context.modules.indice`).

Registrarla en `domain/actions/__init__.py`, en `CATALOG`:

```python
from .indice import IndiceBuild
...
        LlmApply(),
        ReviewScore(),
        External(),
        IndiceBuild(),
```

Desde ahí ya se puede usar en una plantilla: `{"id": "indexar", "action": "indice.build"}` (por la API, como en A.1,
o en `domain/templates.py`).

### 6. Tests

- `tests/pipeline/domain/test_order.py`: una plantilla con la etapa nueva es válida, y sin lo que necesita antes da
  `InvalidTemplate`.
- `tests/pipeline/api/test_executor.py`: un `FakeIndice(IndicePort)` y sumarlo donde se construye `Modules(...)` (los
  tests que ya existen construyen `Modules` y fallan hasta agregarlo); una corrida que llega a la etapa y la completa.
- `tests/pipeline/adapters/test_pipeline_indice_client.py` (los nombres de test no se repiten): `IndiceClient` contra
  `httpx.MockTransport` (lo que manda, lo que lee, un 5xx es `UnavailableError`).

### 7. Documentación

`CLAUDE.md` (sección del pipeline: acciones y módulos que llama), `http/pipeline/*.http`, tareas y roadmap.

## Verificar

```bash
uv run ruff format && uv run ruff check && uv run mypy && uv run pytest
curl localhost:8000/pipeline/actions          # la acción nueva, con needs, gives y descripción
curl localhost:8000/pipeline/health           # "indice": "ok"
curl -XPOST localhost:8000/pipeline/runs -H 'Content-Type: application/json' \
  -d '{"template": "con-indice", "scope": "new", "simulate": true}'
curl localhost:8000/pipeline/runs/<id>        # los registros de cada etapa y sus artefactos
```
