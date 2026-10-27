"""FastAPI application factory for the pipeline (mounted by server at /pipeline)."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from pipeline.adapters import HttpModules, HttpNotifier
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

from .actors import ActorRegistry
from .app_info import VERSION
from .dependencies import ApiSettings
from .executor import Executor
from .routes import ROUTERS

_STATUS: dict[type[PipelineError], int] = {
    InvalidTemplate: 422,
    InvalidRequest: 422,
    ActionError: 422,
    ConflictError: 409,
    NotFoundError: 404,
    UnavailableError: 503,
    RejectedError: 502,
}


async def _http_error(_: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, HTTPException)
    return JSONResponse(status_code=error.status_code, content={"detail": error.detail}, headers=error.headers)


async def _pipeline_error(_: Request, error: Exception) -> JSONResponse:
    code = next((c for kind, c in _STATUS.items() if isinstance(error, kind)), 500)
    return JSONResponse(status_code=code, content={"detail": str(error)})


def create_app(settings: ApiSettings) -> FastAPI:
    app = FastAPI(
        title="prueba-chunking · pipeline",
        version=VERSION,
        description=(
            "A queue of stages run in order, reorderable, with cycles repeated until an actor approves: lab converts"
            " to JSON, lab2 chunks the official JSON, then embeber and modelscenter. Everything over HTTP to ingesta,"
            " chunking and data; the runs are kept in the graph (PIPE_* labels)."
        ),
    )
    session = HttpModules(settings.self_url, settings.ingesta_path, settings.chunking_path, settings.data_path)
    actors = ActorRegistry()

    def answer_route(run: PipelineRun) -> str:
        waiting = run.waiting
        if waiting is None:
            return ""
        kind = "decision" if waiting.stage != waiting.step else "complete"
        return f"{settings.pipeline_path}/runs/{run.id}/stages/{waiting.stage}/{kind}"

    app.state.settings = settings
    app.state.store = session.store
    app.state.actors = actors
    app.state.executor = Executor(session.store, session.modules, HttpNotifier(), actors, answer_route)
    app.add_exception_handler(HTTPException, _http_error)
    app.add_exception_handler(PipelineError, _pipeline_error)
    for router in ROUTERS:
        app.include_router(router)
    return app
