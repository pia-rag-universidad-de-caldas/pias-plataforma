"""Route dependencies: the settings, the registry, the line, the models and the ports over data."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from embeddings.adapters import HttpSession
from embeddings.config import DATA_PATH
from embeddings.models import ChunkSource, ConfigStore, Embedder, RunStore, VectorSink

from .registry import RunRegistry
from .work_queue import WorkQueue


@dataclass(frozen=True)
class ApiSettings:
    self_url: str  # base URL of the server that mounts the modules (ServerSettings.self_url)
    data_path: str = DATA_PATH  # prefix of data in that server: the only module embeddings talks to

    def session(self) -> HttpSession:
        return HttpSession(self.self_url, self.data_path)


def _settings(request: Request) -> ApiSettings:
    settings: ApiSettings = request.app.state.settings
    return settings


def _embedder(request: Request) -> Embedder:
    """One for the whole app: every model stays loaded between requests."""
    embedder: Embedder = request.app.state.embedder
    return embedder


def _registry(request: Request) -> RunRegistry:
    registry: RunRegistry = request.app.state.registry
    return registry


def _queue(request: Request) -> WorkQueue:
    queue: WorkQueue = request.app.state.queue
    return queue


def _session(settings: Annotated[ApiSettings, Depends(_settings)]) -> Iterator[HttpSession]:
    """One HTTP session to data per request."""
    with settings.session() as session:
        yield session


def _source(session: Annotated[HttpSession, Depends(_session)]) -> ChunkSource:
    return session.source


def _vectors(session: Annotated[HttpSession, Depends(_session)]) -> VectorSink:
    return session.vectors


def _config(session: Annotated[HttpSession, Depends(_session)]) -> ConfigStore:
    return session.config


def _runs(session: Annotated[HttpSession, Depends(_session)]) -> RunStore:
    return session.runs


# Types for route parameters: `def route(embedder: Embedding) -> ...`.
Settings = Annotated[ApiSettings, Depends(_settings)]
Embedding = Annotated[Embedder, Depends(_embedder)]
Registry = Annotated[RunRegistry, Depends(_registry)]
Queue = Annotated[WorkQueue, Depends(_queue)]
Source = Annotated[ChunkSource, Depends(_source)]
Vectors = Annotated[VectorSink, Depends(_vectors)]
Config = Annotated[ConfigStore, Depends(_config)]
StoredRuns = Annotated[RunStore, Depends(_runs)]
