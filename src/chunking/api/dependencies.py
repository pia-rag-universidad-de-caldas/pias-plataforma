"""Route dependencies: the settings, the registries, the line and the adapters behind the chunking ports."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from chunking.adapters import HttpServiceProbe, HttpSession
from chunking.config import DATA_PATH
from chunking.models import Chunker, ConfigStore, ExperimentStore, RunStore, ServiceProbe

from .experiments import ExperimentRegistry
from .runs import RunRegistry
from .work_queue import WorkQueue


@dataclass(frozen=True)
class ApiSettings:
    self_url: str  # base URL of the server that mounts the modules (ServerSettings.self_url)
    data_path: str = DATA_PATH  # prefix of data in that server: the only module chunking talks to

    def session(self) -> HttpSession:
        return HttpSession(self.self_url, self.data_path)


def _settings(request: Request) -> ApiSettings:
    settings: ApiSettings = request.app.state.settings
    return settings


def _probe(settings: Annotated[ApiSettings, Depends(_settings)]) -> ServiceProbe:
    return HttpServiceProbe(settings.self_url)


def _chunker(request: Request) -> Chunker:
    """One for the whole app: its tokenizers and chunkers stay loaded."""
    chunker: Chunker = request.app.state.chunker
    return chunker


def _experiments(request: Request) -> ExperimentRegistry:
    registry: ExperimentRegistry = request.app.state.experiments
    return registry


def _runs(request: Request) -> RunRegistry:
    registry: RunRegistry = request.app.state.runs
    return registry


def _queue(request: Request) -> WorkQueue:
    queue: WorkQueue = request.app.state.queue
    return queue


def _store(settings: Annotated[ApiSettings, Depends(_settings)]) -> Iterator[ExperimentStore]:
    """The experiment record and the parsed documents, through data over HTTP; one session per request."""
    with settings.session() as session:
        yield session.experiments


def _config(settings: Annotated[ApiSettings, Depends(_settings)]) -> Iterator[ConfigStore]:
    with settings.session() as session:
        yield session.config


def _run_store(settings: Annotated[ApiSettings, Depends(_settings)]) -> Iterator[RunStore]:
    with settings.session() as session:
        yield session.runs


# Types for route parameters: `def route(chunker: DocumentChunker) -> ...`.
Settings = Annotated[ApiSettings, Depends(_settings)]
Probe = Annotated[ServiceProbe, Depends(_probe)]
DocumentChunker = Annotated[Chunker, Depends(_chunker)]
Queue = Annotated[WorkQueue, Depends(_queue)]
Experiments = Annotated[ExperimentRegistry, Depends(_experiments)]
Runs = Annotated[RunRegistry, Depends(_runs)]
Store = Annotated[ExperimentStore, Depends(_store)]
Config = Annotated[ConfigStore, Depends(_config)]
StoredRuns = Annotated[RunStore, Depends(_run_store)]
