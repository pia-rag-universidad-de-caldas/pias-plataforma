"""FastAPI application factory for the pipeline (mounted by server at /pipeline)."""

from fastapi import FastAPI

from common.api import error_handlers, process_router
from pipeline.adapters import HttpModules, HttpNotifier, callback_hosts
from pipeline.models import (
    ActionError,
    ConflictError,
    InvalidRequest,
    InvalidTemplate,
    NotFoundError,
    PipelineError,
    PipelineRun,
    RejectedError,
    UnavailableError,
)

from .actor_registry import ActorRegistry
from .app_info import VERSION
from .dependencies import ApiSettings
from .executor import Executor
from .processes import PipelineProcesses
from .routes import ROUTERS

_STATUS: dict[type[Exception], int] = {
    InvalidTemplate: 422,
    InvalidRequest: 422,
    ActionError: 422,
    ConflictError: 409,
    NotFoundError: 404,
    UnavailableError: 503,
    RejectedError: 502,
}


def create_app(settings: ApiSettings) -> FastAPI:
    app = FastAPI(
        title="prueba-chunking · pipeline",
        version=VERSION,
        description=(
            "The only one that orchestrates the modules (feature 044): stages run in order, reorderable, with cycles"
            " repeated until an actor approves. produccion: ingesta → parsing → chunking → embeddings, with their"
            " active configurations; laboratorio: a chosen batch, parsed, and lab trying chunking + embeddings"
            " (+ llm) together until it approves a trio. Only ids go between modules; the runs are kept in the graph."
        ),
    )
    session = HttpModules(
        settings.self_url,
        settings.ingesta_path,
        settings.chunking_path,
        settings.data_path,
        parsing_path=settings.parsing_path,
        embeddings_path=settings.embeddings_path,
        llm_path=settings.llm_path,
    )
    actors = ActorRegistry()

    def answer_route(run: PipelineRun) -> str:
        waiting = run.waiting
        if waiting is None:
            return ""
        kind = "decision" if waiting.stage != waiting.step else "complete"
        return f"{settings.pipeline_path}/runs/{run.id}/stages/{waiting.stage}/{kind}"

    hosts = callback_hosts()
    app.state.settings = settings
    app.state.callback_hosts = hosts
    app.state.store = session.store
    app.state.actors = actors
    app.state.executor = Executor(session.store, session.modules, HttpNotifier(hosts=hosts), actors, answer_route)
    app.state.processes = PipelineProcesses(session.store, app.state.executor)
    error_handlers(app, {**_STATUS, PipelineError: 500})  # each error its code; any other one of the pipeline, 500
    for router in ROUTERS:
        app.include_router(router)
    app.include_router(process_router(lambda connection: [connection.app.state.processes]))
    return app
