# Guía: crear un módulo nuevo en `src/`

Paso a paso para sumar un módulo al lado de `ingesta`, `data`, `parsing`, `chunking`, `embeddings`, `llm`,
`pipeline` y `consultas`, montado en el servidor único y visible en la consola. En los ejemplos el módulo se llama **`indice`**: cambiar el nombre en cada paso.

Antes, leer [arquitectura.md](arquitectura.md): capas, qué puede importar quién y cómo se valida un cambio.

## Reglas que no se negocian

- **Un módulo no importa a otro.** Lo que necesita lo pide por HTTP al mismo servidor. Solo `server/` importa a todos.
  Todos pueden importar `common` (feature 033), que no importa a nadie.
- **Decidir antes de empezar qué clase de módulo es** (cambia los pasos 4 y 6):

  | | De trabajo | Consumidor |
  |---|---|---|
  | Ejemplos | `ingesta`, `parsing`, `chunking`, `embeddings`, `llm` | `pipeline`, `consultas` |
  | A quién llama | **solo a `data`** (feature 042), y a lo sumo a un servicio externo que no es un módulo (`llm` → Ollama) | a los módulos que necesite, por su API pública (`consultas` → `embeddings`, `data`, `llm`) |
  | Qué procesa | lo que le pasan (listas de ids); no elige | lo que pide quien lo llama; el pipeline orquesta trabajos, `consultas` responde preguntas |
  | Adaptadores | `adapters/data/` (y el del servicio externo) | un cliente por módulo que llama (`consultas/adapters/embeddings_client.py`, `llm_client.py`, `data_client.py`) |
  | `tests/common/test_module_rule.py` | en el `parametrize`: no puede nombrar rutas de otro módulo que no sea `/data` | fuera del `parametrize`: puede nombrarlas |

  Los dos tienen igual su `ruff.toml` que les prohíbe **importar** a los demás: un consumidor llama por HTTP, nunca
  importa.
- **Código en inglés** (identificadores, docstrings, mensajes, claves JSON nuevas). En español solo lo que se guarda o
  se publica y ya existe así (propiedades del grafo, columnas, valores de categorías).
- **Capas:** `config/` → `models/` → `domain/` (reglas, sin I/O) → `adapters/` (lo único que habla con el exterior) →
  `api/` (lo único que importa FastAPI). Ruff (`TID251`) y mypy `strict` lo hacen cumplir.

## 1. La spec

```
spec/features/NNN-indice/spec.md    # qué y por qué, criterios de aceptación
spec/features/NNN-indice/plan.md    # archivos que se crean y se tocan
spec/features/NNN-indice/tasks.md
```

Sumar la feature a `spec/constitution/roadmap.md`.

## 2. Las carpetas

Copiar la forma de `parsing` o `embeddings` (los módulos de trabajo más nuevos y más simples):

```
src/indice/
├── __init__.py          # docstring: qué hace el módulo (sin código)
├── ruff.toml            # paso 6
├── config/
│   ├── __init__.py      # reexporta las constantes
│   └── settings.py      # valores por defecto, timeouts, páginas (los prefijos vienen de common.config)
├── models/              # un archivo por función: concepts.py, requests.py, results.py, ports.py...
│   └── __init__.py      # reexporta todo: el resto importa `from indice.models import ...`
├── domain/              # reglas de negocio, solo dependen de models y config
│   └── __init__.py
├── adapters/            # una carpeta por el otro lado de la conexión: http/, data/, ingesta/...
│   └── __init__.py
└── api/
    ├── __init__.py      # exporta create_app y ApiSettings
    ├── app.py
    ├── app_info.py      # VERSION = version("prueba-chunking")
    ├── dependencies.py  # ApiSettings y los Depends de las rutas
    ├── schemas.py       # cuerpos de petición y respuesta (dataclasses congeladas)
    ├── processes.py     # su ProcessSource, si corre trabajos (app.state.processes y process_router)
    └── routes/
        ├── __init__.py  # ROUTERS: un APIRouter por archivo
        └── health.py
```

Si el prefijo de varios archivos se repite (`experiment_runner.py`, `experiment_graph.py`), el prefijo es una carpeta
(feature 032).

## 3. La app

`src/indice/api/dependencies.py`:

```python
"""Route dependencies: the app settings."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from indice.config import DATA_PATH


@dataclass(frozen=True)
class ApiSettings:
    self_url: str  # base URL of the server that mounts the modules (ServerSettings.self_url)
    data_path: str = DATA_PATH


def _settings(request: Request) -> ApiSettings:
    settings: ApiSettings = request.app.state.settings
    return settings


Settings = Annotated[ApiSettings, Depends(_settings)]
```

`src/indice/api/app.py`: los errores con `common.api.error_handlers`. Se declara solo qué excepción da qué código; el
cuerpo es `{"detail": mensaje}`, también para el 404 de una URL que no existe.

```python
"""indice HTTP API (FastAPI, feature NNN), mounted by server at /indice."""

from common.api import error_handlers
from fastapi import FastAPI

from indice.models import IndexingError, UpstreamDown

from .app_info import VERSION
from .dependencies import ApiSettings
from .routes import ROUTERS


def create_app(settings: ApiSettings) -> FastAPI:
    app = FastAPI(title="prueba-chunking · indice", version=VERSION, description="What this module does.")
    app.state.settings = settings
    error_handlers(app, {UpstreamDown: 503, IndexingError: 422})
    for router in ROUTERS:
        app.include_router(router)
    return app
```

`src/indice/api/routes/health.py` (todos los módulos tienen uno; el servidor y la consola lo consultan):

```python
"""GET /health: whether the module and what it calls answer."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Always 200: the state of the module."""
    return {"status": "ok"}
```

y en `routes/__init__.py`: `ROUTERS: list[APIRouter] = [health.router]`.

## 4. Hablar con otros módulos

Por HTTP, con el cliente base común. Un módulo de trabajo solo tiene `adapters/data/` (más el cliente de su servicio
externo, si tiene uno: `llm/adapters/ollama_client.py`); un consumidor, un cliente por módulo que llama (ver
`consultas/adapters/`: cada uno con su `ErrorPolicy`, para que un 503 diga qué módulo no respondió). Un cliente por
recurso del otro módulo, en `adapters/<otro>/`:

```python
"""data over HTTP: the JSON nodes."""

import httpx
from common.http import BaseHttpClient, ErrorPolicy, Json, segment

from indice.models import Rejected, UpstreamDown

DATA_ERRORS = ErrorPolicy("data", UpstreamDown, Rejected)  # red/5xx/no-JSON → UpstreamDown; otro 4xx → Rejected


class JsonNodesClient(BaseHttpClient):
    def __init__(self, client: httpx.Client, path: str) -> None:
        super().__init__(client, f"{path.rstrip('/')}/nodes/JSON", DATA_ERRORS)

    def get(self, id: str) -> Json:
        return self._get(f"/{segment(id)}")  # None si es 404
```

- El dominio no ve el cliente: ve un puerto (`Protocol` o `ABC` en `models/ports.py`) que una fachada de `adapters/`
  implementa componiendo clientes (como `GraphDocumentStore` en `chunking/adapters/data/experiment_store.py`).
- Un `httpx.Client` por corrida o por app con `base_url = self_url` (ver `chunking/adapters/session.py`).
- Los nombres en español que vienen de otro módulo se traducen a modelos **solo** en los mappers del adaptador.

## 5. El paquete en el proyecto

`pyproject.toml`:

```toml
[tool.uv.build-backend]
module-name = ["ingesta", "data", "chunking", "pipeline", "server", "common", "parsing", "embeddings", "llm", "consultas", "indice"]

[tool.ruff.lint.per-file-ignores]
"src/indice/adapters/**" = ["TID251"]   # httpx (y lo que use para hablar afuera)
"src/indice/api/**" = ["TID251"]        # FastAPI

[tool.ruff.lint.isort]
known-first-party = [..., "indice"]
```

Si habla con un servicio externo (como `llm` con Ollama), su URL va en su `config/` con una opción de `serve` y una
variable de entorno (`--ollama-url`/`OLLAMA_URL`, en `server/cli.py` y `ServerSettings`), y el servicio puede caer:
un cliente por petición y 503 con el motivo, nunca un 500. Si necesita una dependencia nueva y pesada, va como extra opcional (`[project.optional-dependencies]`), como `parse`
(Docling), `chunk` (docling-core), `embed` (torch) o `data` (neo4j), y el módulo tiene que arrancar sin ella (import
diferido con `import_module` dentro de los métodos, `503` en lo que la necesita y su estado en `GET /indice/health`).
Sumarlo también al `uv export` del trabajo `audit` del CI (`.github/workflows/ci.yml`).

## 6. Que nadie lo importe (y que él no importe a nadie)

`src/indice/ruff.toml`:

```toml
# Ruff for src/indice/ (feature NNN): the root pyproject.toml plus the ban on importing the other modules.
extend = "../../pyproject.toml"

[lint.flake8-tidy-imports.extend-banned-api]
"ingesta".msg = "indice must not import ingesta: modules talk over HTTP; only server/ composes them"
"data".msg = "indice must not import data: modules talk over HTTP; only server/ composes them"
"parsing".msg = "indice must not import parsing: modules talk over HTTP; only server/ composes them"
"chunking".msg = "indice must not import chunking: modules talk over HTTP; only server/ composes them"
"embeddings".msg = "indice must not import embeddings: modules talk over HTTP; only server/ composes them"
"llm".msg = "indice must not import llm: modules talk over HTTP; only server/ composes them"
"pipeline".msg = "indice must not import pipeline: modules talk over HTTP; only server/ composes them"
"consultas".msg = "indice must not import consultas: modules talk over HTTP; only server/ composes them"
"server".msg = "indice must not import server: modules talk over HTTP; only server/ composes them"
```

Y en el `ruff.toml` de **cada uno de los otros** (`src/ingesta/`, `src/data/`, `src/parsing/`, `src/chunking/`,
`src/embeddings/`, `src/llm/`, `src/pipeline/`, `src/consultas/`) una línea más:

```toml
"indice".msg = "<módulo> must not import indice: modules talk over HTTP (feature 020); only server/ composes them"
```

Sumar `"indice"` a `MODULES` en `tests/common/test_independent.py` (lo que `common` no puede importar). Su prefijo va
en `src/common/config.py` (`INDICE_PATH = "/indice"`, junto a los otros). Y en `tests/common/test_module_rule.py`:
su prefijo en `PREFIXES` (para que ningún módulo de trabajo lo nombre) y, si es un módulo de trabajo, su nombre en el
`parametrize` de `test_a_work_module_only_names_data` (hoy `ingesta`, `parsing`, `chunking`, `embeddings`, `llm`); un
consumidor no va ahí.

## 7. Montarlo en el servidor

`src/server/app.py`:

```python
from common.config import INDICE_PATH
from indice.api import ApiSettings as IndiceSettings
from indice.api import create_app as indice_app

INDICE = INDICE_PATH

# dentro de create_app:
indice = indice_app(IndiceSettings(settings.self_url, DATA))
sources = [..., indice.state.processes]   # si corre trabajos: sale en GET /processes y /processes/ws
                                          # (consultas no corre trabajos: no tiene processes ni está en sources)
app.mount(INDICE, indice)

# y en health(), su estado (OK si no tiene nada que abrir; si abre algo, una función _indice_status como las otras):
INDICE.strip("/"): OK,
```

Sumar su `/docs` a la `description` de la app raíz. Si necesita opciones de línea de comandos (`--indice-algo`), van en
`src/server/cli.py` y en `ServerSettings` (`src/server/settings.py`).

## 8. Que aparezca en la consola

En `src/server/console/catalog.py`, una entrada en `MODULES`:

```python
Module("indice", "/indice"),
```

y su nombre y descripción en español en `MODULES` de `texts.py`. Sus rutas salen solas del `openapi.json` del módulo.
Ver [guia-consola.md](guia-consola.md).

## 9. Si el pipeline lo usa

Ver [guia-conectar-pipeline.md](guia-conectar-pipeline.md): un puerto, un cliente, una acción y su cola.

## 10. Tests y archivos `http/`

- `tests/indice/<capa>/test_<archivo>.py`, igual que `src/` (feature 032). Los de `domain/` con puertos falsos que
  implementan solo lo que el código pide; los de `adapters/` contra `httpx.MockTransport`; los de `api/` con
  `fastapi.testclient.TestClient`. Sin `__init__.py`: dos archivos de test no pueden llamarse igual (mypy).
- `http/indice/*.http` para REST Client, como los de los otros módulos.

## 11. Documentación

- `CLAUDE.md`: una sección `## Paquete \`indice\`` (qué hace, capas, rutas) y su línea en la de `server`.
- `docs/arquitectura.md` (la tabla de módulos y el flujo), `docs/api.md` (sus rutas), `README.md` y
  `docs/README.md` si suma una guía, y `spec/constitution/tech-stack.md` (paquetes, extras, límites).
- `tasks.md` tachado y el roadmap.

## 12. Verificar

```bash
uv run ruff format && uv run ruff check && uv run mypy && uv run pytest
NEO4J_PASSWORD=... uv run prueba-chunking serve
curl localhost:8000/indice/health        # el módulo
curl localhost:8000/health               # el servidor lo lista en "modules"
curl localhost:8000/indice/openapi.json  # lo que la consola va a mostrar
uv run prueba-chunking                   # la consola: el módulo en el inicio, sus rutas adentro
```

Comprobar que un import prohibido falla: agregar a propósito `import data` en un archivo de `src/indice/domain/` y
ver que `ruff check` lo rechaza; después quitarlo.
