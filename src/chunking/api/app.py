"""FastAPI application factory for chunking (mounted by server at /chunking)."""

from fastapi import FastAPI

from chunking.adapters import DoclingConverter, Models, SectionStrategies
from chunking.models import DocumentError, SinkError, SourceError
from common.api import error_handlers

from .app_info import VERSION
from .dependencies import ApiSettings
from .experiments import ExperimentRegistry
from .routes import ROUTERS
from .runs import RunRegistry


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
    # ingesta or data (or Neo4j behind it) didn't answer: 503; data rejected the request: 502.
    error_handlers(app, {SinkError: 503, SourceError: 503, DocumentError: 502})
    for router in ROUTERS:
        app.include_router(router)
    return app
