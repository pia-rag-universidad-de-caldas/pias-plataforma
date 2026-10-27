"""Route dependencies: the settings, the run registry and the adapters behind the chunking ports."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from chunking.adapters import HttpServiceProbe, HttpSession
from chunking.config import DATA_PATH, INGESTA_PATH
from chunking.models import ChunkCatalog, Converter, ExperimentStore, SectionChunker, ServiceProbe

from .experiment_registry import ExperimentRegistry
from .registry import RunRegistry


@dataclass(frozen=True)
class ApiSettings:
    self_url: str  # base URL of the server that mounts the modules (ServerSettings.self_url)
    ingesta_path: str = INGESTA_PATH  # prefix of ingesta in that server
    data_path: str = DATA_PATH  # prefix of data in that server


def _settings(request: Request) -> ApiSettings:
    settings: ApiSettings = request.app.state.settings
    return settings


def _probe(settings: Annotated[ApiSettings, Depends(_settings)]) -> ServiceProbe:
    return HttpServiceProbe(settings.self_url)


def _converter(request: Request) -> Converter:
    """One converter for the whole app: it keeps Docling's models loaded between runs."""
    converter: Converter = request.app.state.converter
    return converter


def _registry(request: Request) -> RunRegistry:
    registry: RunRegistry = request.app.state.registry
    return registry


def _experiments(request: Request) -> ExperimentRegistry:
    registry: ExperimentRegistry = request.app.state.experiments
    return registry


def _chunker(request: Request) -> SectionChunker:
    chunker: SectionChunker = request.app.state.chunker
    return chunker


def _store(settings: Annotated[ApiSettings, Depends(_settings)]) -> Iterator[ExperimentStore]:
    """The experiment record, read and written through data over HTTP; one session per request."""
    with HttpSession(settings.self_url, settings.ingesta_path, settings.data_path) as session:
        yield session.experiments


def _catalog(settings: Annotated[ApiSettings, Depends(_settings)]) -> Iterator[ChunkCatalog]:
    """The graph, read through data over HTTP; one session per request."""
    with HttpSession(settings.self_url, settings.ingesta_path, settings.data_path) as session:
        yield session.sink


# Types for route parameters: `def route(converter: DocumentConverter) -> ...`.
Settings = Annotated[ApiSettings, Depends(_settings)]
Probe = Annotated[ServiceProbe, Depends(_probe)]
DocumentConverter = Annotated[Converter, Depends(_converter)]
Registry = Annotated[RunRegistry, Depends(_registry)]
Catalog = Annotated[ChunkCatalog, Depends(_catalog)]
Experiments = Annotated[ExperimentRegistry, Depends(_experiments)]
Chunker = Annotated[SectionChunker, Depends(_chunker)]
Store = Annotated[ExperimentStore, Depends(_store)]
