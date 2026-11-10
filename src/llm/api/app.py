"""FastAPI application factory for llm (mounted by server at /llm): the only module that talks to Ollama."""

from fastapi import FastAPI

from common.api import error_handlers, process_router
from llm.models import DataDown, DataRefused, InvalidChat, ModelsDown

from .app_info import VERSION
from .dependencies import ApiSettings
from .processes import LlmProcesses
from .registry import PullRegistry
from .routes import ROUTERS
from .work_queue import WorkQueue


def create_app(settings: ApiSettings) -> FastAPI:
    app = FastAPI(
        title="prueba-chunking · llm",
        version=VERSION,
        description=(
            "The language models, through Ollama: the admitted ones (config.MODELS), their downloads, the active "
            "configuration (in data) and the chat, with images for a vision model. It knows nothing of documents."
        ),
    )
    app.state.settings = settings
    app.state.registry = PullRegistry()  # the pulls of this session (in memory only)
    app.state.queue = WorkQueue()  # one pull at a time, the others in line
    app.state.processes = LlmProcesses(app.state.queue, app.state.registry)
    # Ollama or data down, or the model not downloaded: 503; data refused what was sent: 502; never a 500 by Ollama.
    error_handlers(app, {ModelsDown: 503, DataDown: 503, DataRefused: 502, InvalidChat: 422})
    for router in ROUTERS:
        app.include_router(router)
    app.include_router(process_router(lambda connection: [connection.app.state.processes]))
    return app
