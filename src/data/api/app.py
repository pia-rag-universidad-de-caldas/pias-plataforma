"""FastAPI application factory for the PIAA graph."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from data.models import GraphAdapter, GraphError

from .app_info import VERSION
from .dependencies import ApiSettings
from .routes import ROUTERS


async def _graph_error(_: Request, error: Exception) -> JSONResponse:
    return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={"detail": str(error)})


async def _http_error(_: Request, error: Exception) -> JSONResponse:
    """HTTP errors (a 404 from a route or from a URL that doesn't exist...) with the same {"detail"} body."""
    assert isinstance(error, HTTPException)
    return JSONResponse(status_code=error.status_code, content={"detail": error.detail}, headers=error.headers)


def create_app(settings: ApiSettings, graph: GraphAdapter) -> FastAPI:
    """The app uses `graph` in every request and closes it on shutdown."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            graph.close()

    app = FastAPI(
        title="prueba-chunking · data",
        version=VERSION,
        description="CRUD of the PIAA graph in Neo4j: nodes by label and relationships allowed by the schema.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.graph = graph
    app.add_exception_handler(GraphError, _graph_error)
    app.add_exception_handler(HTTPException, _http_error)
    for router in ROUTERS:
        app.include_router(router)
    return app
