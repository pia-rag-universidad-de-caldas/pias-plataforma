"""FastAPI application factory for chunking (mounted by server at /chunking)."""

from fastapi import FastAPI

from chunking.adapters import DoclingChunkers
from chunking.models import Chunker, ChunkingRun, DocumentError, ExperimentRecord, SinkError
from common.api import error_handlers, process_router

from .app_info import VERSION
from .dependencies import ApiSettings
from .experiments import ExperimentRegistry
from .processes import ChunkingProcesses
from .routes import ROUTERS
from .runs import RunRegistry
from .work_queue import WorkQueue


def create_app(settings: ApiSettings, chunker: Chunker | None = None) -> FastAPI:
    app = FastAPI(
        title="prueba-chunking · chunking",
        version=VERSION,
        description="Chunking of the parsed documents with docling-core's chunkers; documents and chunks in data.",
    )
    app.state.settings = settings
    app.state.chunker = chunker or DoclingChunkers()  # one for the app: tokenizers and chunkers stay loaded
    app.state.queue = WorkQueue()  # runs and experiments: one at a time, the others in line (feature 039)
    app.state.experiments = ExperimentRegistry(app.state.queue)
    app.state.runs = RunRegistry()

    def stored_experiments() -> list[ExperimentRecord]:
        with settings.session() as session:
            return session.experiments.experiments()

    def stored_runs() -> list[ChunkingRun]:
        with settings.session() as session:
            return session.runs.runs()

    app.state.processes = ChunkingProcesses(
        app.state.queue, app.state.experiments, app.state.runs, stored_experiments, stored_runs
    )
    # data (or Neo4j behind it) didn't answer: 503; data rejected the request: 502.
    error_handlers(app, {SinkError: 503, DocumentError: 502})
    for router in ROUTERS:
        app.include_router(router)
    app.include_router(process_router(lambda connection: [connection.app.state.processes]))
    return app
