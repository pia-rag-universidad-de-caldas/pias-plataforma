# Guía: conectar un módulo al pipeline

El pipeline (`src/pipeline/`, feature 028) corre **plantillas**: etapas en orden, cada una con una **acción**. Una
acción declara qué artefactos necesita (`needs`) y cuáles da (`gives`), y `Order.check` rechaza con 422 un orden en que
a una etapa le falta algo. Hay dos formas de que un módulo participe:

| | A. Actor externo | B. Tarea automática |
|---|---|---|
| Quién hace el trabajo | un proceso que no es del pipeline (otro servicio, una persona, un script) | el pipeline, llamando por HTTP a un módulo de `src/` |
| Código en el pipeline | **ninguno** | un puerto, un cliente, una acción, una cola |
| Cómo se entera | `GET /pipeline/inbox?actor=...` o un aviso POST a su `callback_url` | — |
| Cómo responde | `POST /pipeline/runs/{id}/stages/{etapa}/complete` | lo que devuelve su acción |
| Ejemplos hoy | `embeber`, `modelscenter` | `ingesta.select`, `chunking.convert`, `data.promote_chunks` |

Si el módulo hace un trabajo largo o vive fuera del servidor, empezar por **A**: no toca código y se puede pasar a B
después.

## A. Como actor externo (sin código)

### 1. Ponerlo en la plantilla

Una etapa con la acción `external`, su `actor` y lo que necesita y da (nombres de artefactos):

```json
{"id": "indexar", "action": "external", "actor": "indexador", "needs": ["fragmentos_oficiales"], "gives": ["indice"]}
```

Claves admitidas de una etapa: `id`, `action`, `params`, `actor`, `stages`, `max_iterations`, `needs`, `gives`.
`needs` tiene que darlo una etapa anterior (si no, 422 con el nombre de la etapa). Los artefactos que ya existen están
en `src/pipeline/models/concepts.py` (`FILE_BATCH = "lote_archivos"`, `OFFICIAL_JSON = "json_oficial"`,
`OFFICIAL_CHUNKS`, `EMBEDDINGS = "embeddings"`, `REVIEW = "revision"`...; `GET /pipeline/actions` los lista por acción).

Para agregarla:

```bash
curl localhost:8000/pipeline/pipelines/piaa                       # las etapas actuales
curl -XPUT localhost:8000/pipeline/pipelines/piaa -H 'Content-Type: application/json' \
  -d '{"stages": [ ...las de antes..., {"id": "indexar", "action": "external", "actor": "indexador",
       "needs": ["fragmentos_oficiales"], "gives": ["indice"]}]}'
# o una plantilla nueva: POST /pipeline/pipelines {"id": "con-indice", "stages": [...]}
# reordenar: PUT /pipeline/pipelines/{id}/stages {"order": [...]}  o  POST .../stages/{etapa}/move {"after": "..."}
```

`piaa` es la plantilla incorporada (`domain/templates.py`): se puede modificar por la API pero no borrar. Para que
**siempre** traiga la etapa nueva, agregarla en `domain/templates.py` (y su test en `tests/pipeline/domain/test_order.py`:
`test_the_builtin_template_is_valid`).

### 2. Registrar el actor (si quiere aviso)

```bash
curl -XPUT localhost:8000/pipeline/actors/indexador -H 'Content-Type: application/json' \
  -d '{"callback_url": "http://mi-servicio/avisos"}'
```

Sin `callback_url` igual funciona: el actor consulta su bandeja. Ojo: hoy los actores viven en memoria
(`api/actor_registry.py`) y se pierden al reiniciar el servidor; los conocidos al arrancar están en
`config.ACTORS`.

### 3. Lo que recibe

Cuando una corrida llega a su etapa, queda `waiting`; el actor la ve en `GET /pipeline/inbox?actor=indexador` y, si
tiene `callback_url`, recibe un POST (sin reintentos; si falla, queda un evento `notify_failed` en la corrida y la
etapa sigue en la bandeja) con:

```json
{"run": "...", "name": "...", "stage": "indexar", "step": "indexar", "actor": "indexador", "since": "...",
 "iteration": null, "exhausted": false, "experiment": null, "batch": ["sha256", "..."],
 "artifacts": {"fragmentos_oficiales": ["..."]}, "answer": "/pipeline/runs/<id>/stages/indexar/complete"}
```

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
`POST .../stages/{ciclo}/decision` con `{"decision": "retry", "next": {...}}` (`next` se fusiona con la configuración
de la iteración anterior) o `{"decision": "approve"}` (por defecto aprueba la última; `"iteration": n` elige otra). Lo que da un ciclo
aprobado es la versión aprobada de lo que dan sus etapas. Ver `conversion` y `chunking` en `domain/templates.py`.

## B. Como tarea automática (un módulo de `src/`)

El pipeline nunca importa a otro módulo: lo llama por HTTP. El ejemplo conecta un módulo **`indice`** montado en
`/indice` que expone `POST /indice/builds` (si el módulo aún no existe, ver [guia-nuevo-modulo.md](guia-nuevo-modulo.md)).

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
    chunking: ChunkingPort
    data: DataPort
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

Un 409 que hay que esperar (como el de chunking cuando hay otra corrida) se maneja con `_send` + `CONFLICT` +
`_rejected`: ver `ChunkingClient.run_experiment`. Si la respuesta tiene muchos campos, su lectura va en
`adapters/mappers.py`.

### 3. Dónde está (`config`, sesión, servidor)

- `src/pipeline/config/settings.py`: `INDICE_PATH = "/indice"` (y en `config/__init__.py`).
- `src/pipeline/api/dependencies.py`: `indice_path: str = INDICE_PATH` en `ApiSettings`.
- `src/pipeline/adapters/session.py`: el parámetro en `HttpModules` y `IndiceClient(self._client, indice_path)` dentro
  de `Modules(...)`.
- `src/pipeline/api/app.py`: pasar `settings.indice_path` a `HttpModules`.
- `src/pipeline/api/routes/health.py`: `"indice": settings.indice_path` en `paths`, para que `GET /pipeline/health`
  diga si responde.
- `src/server/app.py`: `PipelineSettings(settings.self_url, INGESTA, CHUNKING, DATA, PIPELINE, INDICE)` (en el orden
  de los campos de `ApiSettings`).

### 4. La cola (`src/pipeline/api/executor.py`)

Cada acción corre en la cola de su `module`: un trabajador por cola, en orden de llegada. **Sumar `"indice"` a
`QUEUES`**; si no, la tarea falla al encolarse (`KeyError` en `Executor._continue`) y la corrida no avanza.

```python
QUEUES = ("ingesta", "chunking", "data", "indice")
```

### 5. La acción (`src/pipeline/domain/actions/indice.py`)

```python
"""Building the index of the official chunks (feature NNN)."""

from pipeline.models import OFFICIAL_CHUNKS, Action, ActionContext, ActionError, ActionOutput, StageKind

INDEX = "indice"  # the artifact it gives (better: a constant in models/concepts.py, next to the others)


class IndiceBuild(Action):
    name = "indice.build"
    kind = StageKind.TASK
    module = "indice"  # its queue
    needs = (OFFICIAL_CHUNKS,)
    gives = (INDEX,)
    description = "builds the index of the official chunks"
    parameters = "none"  # what it reads from its configuration (shown in GET /pipeline/actions)

    def run(self, context: ActionContext) -> ActionOutput:
        chunks = context.artifacts.get(OFFICIAL_CHUNKS)
        if not isinstance(chunks, list) or not chunks:
            raise ActionError(f"{context.stage.id}: there are no official chunks")
        id = context.modules.indice.build(tuple(str(s) for s in chunks))
        return ActionOutput({INDEX: id}, {"index": id})
```

- `context.config` es la configuración de la etapa (sus `params`, los de la corrida para esa etapa y, en un ciclo, los
  de la iteración); `context.artifacts`, lo que dieron las etapas anteriores.
- Un error esperado es `ActionError` (la corrida queda `failed`, se reintenta con `resume`); `UnavailableError` y
  `RejectedError` del cliente también fallan la etapa.
- Sin HTTP aquí: solo el puerto (`context.modules.indice`).

Registrarla en `domain/actions/__init__.py`, en `CATALOG`:

```python
from .indice import IndiceBuild
...
        External(),
        IndiceBuild(),
```

Desde ahí ya se puede usar en una plantilla: `{"id": "indexar", "action": "indice.build"}` (por la API, como en A.1,
o en `domain/templates.py`).

### 6. Tests

- `tests/pipeline/domain/test_order.py`: una plantilla con la etapa nueva es válida, y sin lo que necesita antes da
  `InvalidTemplate`.
- `tests/pipeline/api/test_executor.py`: un `FakeIndice(IndicePort)` y sumarlo a `Modules(FakeIngesta(), chunking,
  FakeData(), FakeIndice())` (los tests que ya existen construyen `Modules` y fallan hasta agregarlo); una corrida que
  llega a la etapa y la completa.
- `tests/pipeline/adapters/test_clients.py`: `IndiceClient` contra `httpx.MockTransport` (lo que manda, lo que lee,
  un 5xx es `UnavailableError`).

### 7. Documentación

`CLAUDE.md` (sección del pipeline: acciones y módulos que llama), `http/pipeline/*.http`, tareas y roadmap.

## Verificar

```bash
uv run ruff format && uv run ruff check && uv run mypy && uv run pytest
curl localhost:8000/pipeline/actions          # la acción nueva, con needs, gives y descripción
curl localhost:8000/pipeline/health           # "indice": "ok"
curl -XPOST localhost:8000/pipeline/runs -H 'Content-Type: application/json' \
  -d '{"template": "con-indice", "files": {"pages": {"from": 1, "to": 1}, "per_page": 2, "types": ["pdf"]}}'
curl localhost:8000/pipeline/runs/<id>        # los registros de cada etapa y sus artefactos
```
