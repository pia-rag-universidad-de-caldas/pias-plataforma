"""FastAPI application factory for the PIAA graph."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, status

from common.api import error_handlers
from data.models import GraphAdapter, GraphError

from .app_info import VERSION
from .dependencies import ApiSettings
from .routes import ROUTERS


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
    error_handlers(app, {GraphError: status.HTTP_503_SERVICE_UNAVAILABLE})
    for router in ROUTERS:
        app.include_router(router)
    return app
