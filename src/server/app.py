"""Root FastAPI app: mounts the app of each module (built with its own create_app) under its prefix.

Mounting (instead of include_router) keeps each module's error handlers, {"detalle"}/{"detail"} format and /docs.
Starlette doesn't run the lifespan of mounted apps, so the root lifespan closes the graph that data uses.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI

from chunking.api import ApiSettings as ChunkingSettings
from chunking.api import create_app as chunking_app
from data.api import create_app as data_app
from data.models import GraphAdapter, GraphError
from ingesta.adapters import SQLORMAdapter
from ingesta.api import create_app as ingesta_app
from ingesta.models import MemoryStoreError
from ingesta.tables import TABLES
from pipeline.api import ApiSettings as PipelineSettings
from pipeline.api import create_app as pipeline_app

from .graph import open_graph
from .schemas import ModuleStatus, ServerHealth
from .settings import ServerSettings

VERSION = version("prueba-chunking")
OK = ModuleStatus("ok")

# Prefix of each module in the server.
INGESTA = "/ingesta"
DATA = "/data"
CHUNKING = "/chunking"
PIPELINE = "/pipeline"


def _ingesta_status(memory: str) -> ModuleStatus:
    try:
        SQLORMAdapter.from_existing(memory, TABLES).close()
    except MemoryStoreError as error:
        return ModuleStatus("unavailable", str(error))
    return OK


def _data_status(graph: GraphAdapter) -> ModuleStatus:
    try:
        graph.verify()
    except GraphError as error:
        return ModuleStatus("unavailable", str(error))
    return OK


def create_app(settings: ServerSettings, graph: GraphAdapter | None = None) -> FastAPI:
    """The server app. `graph` defaults to open_graph(settings); it is opened here, once, and closed on shutdown."""
    graph = graph or open_graph(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            graph.close()

    app = FastAPI(
        title="prueba-chunking",
        version=VERSION,
        description=(
            f"Single server: each module under its prefix, with its own docs: [{INGESTA}/docs]({INGESTA}/docs), "
            f"[{DATA}/docs]({DATA}/docs), [{CHUNKING}/docs]({CHUNKING}/docs), [{PIPELINE}/docs]({PIPELINE}/docs)."
        ),
        lifespan=lifespan,
    )
    app.state.settings = settings

    @app.get("/health", tags=["health"])
    def health() -> ServerHealth:
        """State of each module, checked in process (without HTTP); always 200, it is only a diagnosis."""
        modules = {
            INGESTA.strip("/"): _ingesta_status(settings.ingesta.memory),
            DATA.strip("/"): _data_status(graph),
            CHUNKING.strip("/"): OK,  # it has nothing to open; GET /chunking/health checks Docling and the others
            PIPELINE.strip("/"): OK,  # same: GET /pipeline/health checks the modules it calls
        }
        healthy = all(m.status == OK.status for m in modules.values())
        return ServerHealth(status="ok" if healthy else "degraded", version=VERSION, modules=modules)

    app.mount(INGESTA, ingesta_app(settings.ingesta))
    app.mount(DATA, data_app(settings.data, graph))
    app.mount(CHUNKING, chunking_app(ChunkingSettings(settings.self_url, INGESTA, DATA)))
    app.mount(PIPELINE, pipeline_app(PipelineSettings(settings.self_url, INGESTA, CHUNKING, DATA, PIPELINE)))
    return app
