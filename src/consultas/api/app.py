"""FastAPI application factory for consultas (mounted by server at /consultas): the RAG."""

from fastapi import FastAPI

from common.api import error_handlers
from consultas.adapters import HttpModules
from consultas.models import (
    Conflict,
    ConsultasError,
    InvalidQuestion,
    ModuleDown,
    NotFound,
    NoVisionModel,
    Rejected,
)

from .app_info import VERSION
from .dependencies import ApiSettings
from .routes import ROUTERS

_STATUS: dict[type[Exception], int] = {
    ModuleDown: 503,
    NoVisionModel: 503,  # an image, and llm has no vision model downloaded
    InvalidQuestion: 422,
    NotFound: 404,
    Conflict: 409,
    Rejected: 502,
}


def create_app(settings: ApiSettings, modules: HttpModules | None = None) -> FastAPI:
    """`modules` defaults to the HTTP clients against settings.self_url, one for the app."""
    app = FastAPI(
        title="prueba-chunking · consultas",
        version=VERSION,
        description=(
            "Questions answered with the official documents (feature 048): the question becomes a vector (embeddings),"
            " data finds the closest chunks, llm answers with them as context and data keeps the chat. Every answer"
            " cites its sources; if no chunk passes min_score, the LLM isn't called. With `against`, the chunks of an"
            " embeddings experiment, nothing official. With `attachments`, documents (read by parsing, never stored)"
            " and images (described by a vision model of llm) search what is similar to them."
        ),
    )
    app.state.settings = settings
    app.state.modules = modules or settings.modules()
    error_handlers(app, {**_STATUS, ConsultasError: 500})  # each error its code; any other one of consultas, 500
    for router in ROUTERS:
        app.include_router(router)
    return app
