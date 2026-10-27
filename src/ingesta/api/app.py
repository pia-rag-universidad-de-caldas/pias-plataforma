"""FastAPI application factory."""

from fastapi import FastAPI, status

from common.api import error_handlers
from ingesta.models import FileError, MemoryStoreError

from .app_info import VERSION
from .dependencies import ApiSettings
from .ingestion_registry import IngestionRegistry
from .routes import ROUTERS


def create_app(settings: ApiSettings) -> FastAPI:
    app = FastAPI(
        title="prueba-chunking · ingesta",
        version=VERSION,
        description="Ingest (also started from here), classification and statistics of the data/base/ documents.",
    )
    app.state.settings = settings
    app.state.ingestions = IngestionRegistry()  # the ingestions started from the API (feature 030)
    # Response key: stays in Spanish.
    error_handlers(
        app,
        {MemoryStoreError: status.HTTP_503_SERVICE_UNAVAILABLE, FileError: status.HTTP_500_INTERNAL_SERVER_ERROR},
        key="detalle",
    )
    for router in ROUTERS:
        app.include_router(router)
    return app
