"""FastAPI application factory for embeddings (mounted by server at /embeddings): the only module that loads
embedding models."""

from fastapi import FastAPI

from common.api import error_handlers, process_router
from embeddings.adapters import LocalModels
from embeddings.models import DocumentError, Embedder, EmbeddingRun, InvalidLimit, RunKind, UpstreamDown

from .app_info import VERSION
from .dependencies import ApiSettings
from .history import stored_runs
from .processes import EmbeddingProcesses
from .registry import RunRegistry
from .routes import ROUTERS
from .work_queue import WorkQueue


def create_app(settings: ApiSettings, embedder: Embedder | None = None) -> FastAPI:
    """`embedder` defaults to LocalModels, one for the app: every model stays loaded between requests."""
    app = FastAPI(
        title="prueba-chunking · embeddings",
        version=VERSION,
        description=(
            "Vectors of the official chunks (FRAGMENTOS) and of the chunks of chunking experiments (EXP_CHUNK), kept "
            "in data, and texts turned into vectors for whoever searches (POST /vectors). It only talks to data; it "
            "embeds exactly what it is given."
        ),
    )
    app.state.settings = settings
    app.state.embedder = embedder or LocalModels()
    app.state.registry = RunRegistry()  # the runs and experiments of this session
    app.state.queue = WorkQueue()  # one at a time, the others in line

    def stored() -> list[EmbeddingRun]:
        with settings.session() as session:
            return [*stored_runs(session.runs, RunKind.RUN), *stored_runs(session.runs, RunKind.EXPERIMENT)]

    app.state.processes = EmbeddingProcesses(app.state.queue, app.state.registry, stored)
    # data (or Neo4j behind it) or the model didn't answer: 503; data refused what was sent: 502.
    error_handlers(app, {UpstreamDown: 503, DocumentError: 502, InvalidLimit: 422})
    for router in ROUTERS:
        app.include_router(router)
    app.include_router(process_router(lambda connection: [connection.app.state.processes]))
    return app
