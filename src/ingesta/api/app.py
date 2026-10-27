"""FastAPI application factory."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from ingesta.models import FileError, MemoryStoreError

from .app_info import VERSION
from .dependencies import ApiSettings
from .ingestions import IngestionRegistry
from .routes import ROUTERS


def _error_response(code: int, error: Exception) -> JSONResponse:
    return JSONResponse(status_code=code, content={"detalle": str(error)})  # response key: stays in Spanish


async def _memory_error(_: Request, error: Exception) -> JSONResponse:
    return _error_response(status.HTTP_503_SERVICE_UNAVAILABLE, error)


async def _file_error(_: Request, error: Exception) -> JSONResponse:
    return _error_response(status.HTTP_500_INTERNAL_SERVER_ERROR, error)


async def _http_error(_: Request, error: Exception) -> JSONResponse:
    """HTTP errors (a 404 from a route or from a URL that doesn't exist...) with the same {"detalle"} body."""
    assert isinstance(error, HTTPException)
    return JSONResponse(status_code=error.status_code, content={"detalle": error.detail}, headers=error.headers)


def create_app(settings: ApiSettings) -> FastAPI:
    app = FastAPI(
        title="prueba-chunking · ingesta",
        version=VERSION,
        description="Ingest (also started from here), classification and statistics of the data/base/ documents.",
    )
    app.state.settings = settings
    app.state.ingestions = IngestionRegistry()  # the ingestions started from the API (feature 030)
    app.add_exception_handler(MemoryStoreError, _memory_error)
    app.add_exception_handler(FileError, _file_error)
    app.add_exception_handler(HTTPException, _http_error)
    for router in ROUTERS:
        app.include_router(router)
    return app
