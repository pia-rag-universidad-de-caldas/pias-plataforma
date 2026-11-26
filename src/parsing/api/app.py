"""FastAPI application factory for parsing (mounted by server at /parsing)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from common.api import error_handlers, process_router
from parsing.adapters import DoclingParser
from parsing.models import DocumentError, Parser, ParsingRun, SinkError

from .app_info import VERSION
from .dependencies import ApiSettings
from .history import stored_runs
from .preview_slot import PreviewSlot
from .processes import ParsingProcesses
from .registry import RunRegistry
from .routes import ROUTERS
from .work_queue import WorkQueue


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    app.state.previews.close()


def create_app(settings: ApiSettings, parser: Parser | None = None) -> FastAPI:
    """`parser` defaults to a DoclingParser, one for the app: Docling's models stay loaded between runs."""
    app = FastAPI(
        title="prueba-chunking · parsing",
        version=VERSION,
        description=(
            "Parsing with Docling, with one fixed configuration: the RAW files of data become JSON documents in data. "
            "It only talks to data; it parses exactly the sha256 it is given. POST /preview reads a document with the "
            "same configuration and answers its text without storing anything (feature 048)."
        ),
        lifespan=_lifespan,
    )
    app.state.settings = settings
    app.state.parser = parser or DoclingParser()
    app.state.registry = RunRegistry()  # the runs of this session
    app.state.queue = WorkQueue()  # one at a time, the others in line
    app.state.previews = PreviewSlot()  # POST /preview: one at a time, apart from the runs

    def stored() -> list[ParsingRun]:
        with settings.session() as session:
            return stored_runs(session.runs)

    app.state.processes = ParsingProcesses(app.state.queue, app.state.registry, stored)
    # data (or Neo4j behind it) didn't answer: 503; data refused what was asked: 502.
    error_handlers(app, {SinkError: 503, DocumentError: 502})
    for router in ROUTERS:
        app.include_router(router)
    app.include_router(process_router(lambda connection: [connection.app.state.processes]))
    return app
