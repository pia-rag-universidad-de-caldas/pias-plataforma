"""FastAPI application factory for chunking (mounted by server at /chunking)."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from chunking.adapters import DoclingConverter, Models, SectionStrategies
from chunking.models import DocumentError, SinkError, SourceError

from .app_info import VERSION
from .dependencies import ApiSettings
from .experiment_registry import ExperimentRegistry
from .registry import RunRegistry
from .routes import ROUTERS


async def _http_error(_: Request, error: Exception) -> JSONResponse:
    """HTTP errors (a 404 from a route or from a URL that doesn't exist...) with the {"detail"} body."""
    assert isinstance(error, HTTPException)
    return JSONResponse(status_code=error.status_code, content={"detail": error.detail}, headers=error.headers)


async def _data_down(_: Request, error: Exception) -> JSONResponse:
    """ingesta or data (or Neo4j behind it) didn't answer: 503; data rejected the request: 502."""
    code = 503 if isinstance(error, SinkError | SourceError) else 502
    return JSONResponse(status_code=code, content={"detail": str(error)})


def create_app(settings: ApiSettings) -> FastAPI:
    app = FastAPI(
        title="prueba-chunking · chunking",
        version=VERSION,
        description="Chunking of the chunkable documents with Docling; documents from ingesta, chunks to data.",
    )
    app.state.settings = settings
    models = Models()  # tokenizers and embedding models, loaded once for the app
    app.state.converter = DoclingConverter(models)  # one for the app: Docling's models stay loaded between runs
    app.state.chunker = SectionStrategies(models)  # the strategies of experiments (feature 025)
    app.state.registry = RunRegistry()  # the production runs of this session (feature 023)
    app.state.experiments = ExperimentRegistry()  # the experiment this server is running (feature 025)
    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(SinkError, _data_down)
    app.add_exception_handler(DocumentError, _data_down)
    app.add_exception_handler(SourceError, _data_down)
    for router in ROUTERS:
        app.include_router(router)
    return app
