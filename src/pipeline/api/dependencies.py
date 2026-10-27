"""Route dependencies: the settings and the app's store, executor, actors and templates."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from pipeline.config import CHUNKING_PATH, DATA_PATH, INGESTA_PATH
from pipeline.models import RunStore

from .actor_registry import ActorRegistry
from .executor import Executor

PIPELINE_PATH = "/pipeline"


@dataclass(frozen=True)
class ApiSettings:
    self_url: str  # base URL of the server that mounts the modules (ServerSettings.self_url)
    ingesta_path: str = INGESTA_PATH
    chunking_path: str = CHUNKING_PATH
    data_path: str = DATA_PATH
    pipeline_path: str = PIPELINE_PATH  # its own prefix, for the answer routes it tells the actors


def _settings(request: Request) -> ApiSettings:
    settings: ApiSettings = request.app.state.settings
    return settings


def _store(request: Request) -> RunStore:
    store: RunStore = request.app.state.store
    return store


def _executor(request: Request) -> Executor:
    executor: Executor = request.app.state.executor
    return executor


def _actors(request: Request) -> ActorRegistry:
    actors: ActorRegistry = request.app.state.actors
    return actors


Settings = Annotated[ApiSettings, Depends(_settings)]
Store = Annotated[RunStore, Depends(_store)]
Runner = Annotated[Executor, Depends(_executor)]
Actors = Annotated[ActorRegistry, Depends(_actors)]
