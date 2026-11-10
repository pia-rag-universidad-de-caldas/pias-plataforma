"""Root FastAPI app: mounts the app of each module (built with its own create_app) under its prefix.

Mounting (instead of include_router) keeps each module's error handlers, {"detalle"}/{"detail"} format and /docs.
Starlette doesn't run the lifespan of mounted apps, so the root lifespan closes the graph that data uses.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from importlib.metadata import version

from fastapi import FastAPI

from chunking.api import ApiSettings as ChunkingSettings
from chunking.api import create_app as chunking_app
from common.api import BodyLimit, HostGuard, process_router
from common.config import (
    CHUNKING_PATH,
    CONSULTAS_PATH,
    DATA_PATH,
    EMBEDDINGS_PATH,
    INGESTA_PATH,
    LLM_PATH,
    PARSING_PATH,
    PIPELINE_PATH,
)
from consultas.api import ApiSettings as ConsultasSettings
from consultas.api import create_app as consultas_app
from data.api import create_app as data_app
from data.models import GraphAdapter, GraphError
from embeddings.api import ApiSettings as EmbeddingsSettings
from embeddings.api import create_app as embeddings_app
from ingesta.adapters import SQLORMAdapter
from ingesta.api import create_app as ingesta_app
from ingesta.models import MemoryStoreError
from ingesta.tables import TABLES
from llm.api import ApiSettings as LlmSettings
from llm.api import create_app as llm_app
from parsing.api import ApiSettings as ParsingSettings
from parsing.api import create_app as parsing_app
from pipeline.api import ApiSettings as PipelineSettings
from pipeline.api import create_app as pipeline_app

from .graph import open_graph
from .schemas import ModuleStatus, ServerHealth
from .settings import ServerSettings

VERSION = version("prueba-chunking")
OK = ModuleStatus("ok")

# Prefix of each module in the server.
INGESTA = INGESTA_PATH
DATA = DATA_PATH
CHUNKING = CHUNKING_PATH
PIPELINE = PIPELINE_PATH
PARSING = PARSING_PATH
EMBEDDINGS = EMBEDDINGS_PATH
LLM = LLM_PATH
CONSULTAS = CONSULTAS_PATH
MODULE_PREFIXES = (INGESTA, DATA, PARSING, CHUNKING, EMBEDDINGS, LLM, CONSULTAS, PIPELINE)  # what the server mounts


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
            f"[{DATA}/docs]({DATA}/docs), [{PARSING}/docs]({PARSING}/docs), [{CHUNKING}/docs]({CHUNKING}/docs), "
            f"[{EMBEDDINGS}/docs]({EMBEDDINGS}/docs), [{LLM}/docs]({LLM}/docs), [{CONSULTAS}/docs]({CONSULTAS}/docs), "
            f"[{PIPELINE}/docs]({PIPELINE}/docs)."
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
            PARSING.strip("/"): OK,  # it has nothing to open; GET /parsing/health checks Docling, the OCR and data
            CHUNKING.strip("/"): OK,  # it has nothing to open; GET /chunking/health checks Docling and the others
            EMBEDDINGS.strip("/"): OK,  # same: GET /embeddings/health checks torch, transformers and data
            LLM.strip("/"): OK,  # same: GET /llm/health checks Ollama and data
            PIPELINE.strip("/"): OK,  # same: GET /pipeline/health checks the modules it calls
            CONSULTAS.strip("/"): OK,  # same: GET /consultas/health checks embeddings, llm and data
        }
        healthy = all(m.status == OK.status for m in modules.values())
        return ServerHealth(status="ok" if healthy else "degraded", version=VERSION, modules=modules)

    # ingesta publishes the chunkable files in data (feature 042): it needs where the server is and data's limit.
    ingesta = ingesta_app(replace(settings.ingesta, self_url=settings.self_url, raw_limit=settings.max_body_bytes))
    parsing = parsing_app(ParsingSettings(settings.self_url, DATA))
    chunking = chunking_app(ChunkingSettings(settings.self_url, DATA))
    embeddings = embeddings_app(EmbeddingsSettings(settings.self_url, DATA))
    llm = llm_app(LlmSettings(settings.self_url, DATA, settings.ollama_url))
    pipeline = pipeline_app(PipelineSettings(settings.self_url, INGESTA, CHUNKING, DATA, PIPELINE))
    consultas = consultas_app(  # no processes
        ConsultasSettings(settings.self_url, EMBEDDINGS, LLM_PATH, DATA, parsing_path=PARSING)
    )
    # Every process of the server (feature 039): GET /processes and the WebSocket /processes/ws.
    sources = [
        ingesta.state.processes,
        parsing.state.processes,
        chunking.state.processes,
        embeddings.state.processes,
        llm.state.processes,
        pipeline.state.processes,
    ]
    app.include_router(process_router(lambda _: sources))
    app.mount(INGESTA, ingesta)
    app.mount(DATA, data_app(settings.data, graph))
    app.mount(PARSING, parsing)
    app.mount(CHUNKING, chunking)
    app.mount(EMBEDDINGS, embeddings)
    app.mount(LLM, llm)
    app.mount(PIPELINE, pipeline)
    app.mount(CONSULTAS, consultas)
    app.add_middleware(BodyLimit, limit=settings.max_body_bytes)
    app.add_middleware(HostGuard, hosts=settings.trusted_hosts)  # added last: it runs first
    return app
