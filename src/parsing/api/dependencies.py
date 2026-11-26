"""Route dependencies: the settings, the registry, the line, the parser and the ports over data."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from parsing.adapters import HttpSession
from parsing.config import DATA_PATH
from parsing.models import ParsedSink, Parser, RawSource, RunStore

from .preview_slot import PreviewSlot
from .registry import RunRegistry
from .work_queue import WorkQueue


@dataclass(frozen=True)
class ApiSettings:
    self_url: str  # base URL of the server that mounts the modules (ServerSettings.self_url)
    data_path: str = DATA_PATH  # prefix of data in that server: the only module parsing talks to

    def session(self) -> HttpSession:
        return HttpSession(self.self_url, self.data_path)


def _settings(request: Request) -> ApiSettings:
    settings: ApiSettings = request.app.state.settings
    return settings


def _parser(request: Request) -> Parser:
    """One parser for the whole app: it keeps Docling's models loaded between runs."""
    parser: Parser = request.app.state.parser
    return parser


def _registry(request: Request) -> RunRegistry:
    registry: RunRegistry = request.app.state.registry
    return registry


def _queue(request: Request) -> WorkQueue:
    queue: WorkQueue = request.app.state.queue
    return queue


def _previews(request: Request) -> PreviewSlot:
    previews: PreviewSlot = request.app.state.previews
    return previews


def _session(settings: Annotated[ApiSettings, Depends(_settings)]) -> Iterator[HttpSession]:
    """One HTTP session to data per request."""
    with settings.session() as session:
        yield session


def _raws(session: Annotated[HttpSession, Depends(_session)]) -> RawSource:
    return session.raws


def _sink(session: Annotated[HttpSession, Depends(_session)]) -> ParsedSink:
    return session.parsed


def _runs(session: Annotated[HttpSession, Depends(_session)]) -> RunStore:
    return session.runs


# Types for route parameters: `def route(parser: DocumentParser) -> ...`.
Settings = Annotated[ApiSettings, Depends(_settings)]
DocumentParser = Annotated[Parser, Depends(_parser)]
Registry = Annotated[RunRegistry, Depends(_registry)]
Queue = Annotated[WorkQueue, Depends(_queue)]
Previews = Annotated[PreviewSlot, Depends(_previews)]
Raws = Annotated[RawSource, Depends(_raws)]
Sink = Annotated[ParsedSink, Depends(_sink)]
StoredRuns = Annotated[RunStore, Depends(_runs)]
