"""Route dependencies: the settings, the pulls, the line, Ollama and the active configuration over data."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from llm.adapters import HttpSession, OllamaClient
from llm.config import DATA_PATH, OLLAMA_URL
from llm.models import ConfigStore, LanguageModels

from .registry import PullRegistry
from .work_queue import WorkQueue


@dataclass(frozen=True)
class ApiSettings:
    self_url: str  # base URL of the server that mounts the modules (ServerSettings.self_url)
    data_path: str = DATA_PATH  # prefix of data in that server: where the active configuration is
    ollama_url: str = OLLAMA_URL  # Ollama, the only one that runs the models

    def session(self) -> HttpSession:
        return HttpSession(self.self_url, self.data_path)

    def ollama(self, timeout: float | None = None) -> OllamaClient:
        """`timeout`: of the quick requests (health); the chat and the pull keep their own."""
        return OllamaClient(self.ollama_url) if timeout is None else OllamaClient(self.ollama_url, timeout)


def _settings(request: Request) -> ApiSettings:
    settings: ApiSettings = request.app.state.settings
    return settings


def _registry(request: Request) -> PullRegistry:
    registry: PullRegistry = request.app.state.registry
    return registry


def _queue(request: Request) -> WorkQueue:
    queue: WorkQueue = request.app.state.queue
    return queue


def _session(settings: Annotated[ApiSettings, Depends(_settings)]) -> Iterator[HttpSession]:
    """One HTTP session to data per request."""
    with settings.session() as session:
        yield session


def _config(session: Annotated[HttpSession, Depends(_session)]) -> ConfigStore:
    return session.config


def _ollama(settings: Annotated[ApiSettings, Depends(_settings)]) -> Iterator[LanguageModels]:
    """One client of Ollama per request."""
    with settings.ollama() as ollama:
        yield ollama


# Types for route parameters: `def route(ollama: Ollama) -> ...`.
Settings = Annotated[ApiSettings, Depends(_settings)]
Registry = Annotated[PullRegistry, Depends(_registry)]
Queue = Annotated[WorkQueue, Depends(_queue)]
Config = Annotated[ConfigStore, Depends(_config)]
Ollama = Annotated[LanguageModels, Depends(_ollama)]
