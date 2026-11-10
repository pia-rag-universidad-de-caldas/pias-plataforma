"""Route dependencies: the settings and, over the app's HTTP clients, the Asker and the ports."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from consultas.adapters import HttpModules
from consultas.config import DATA_PATH, EMBEDDINGS_PATH, LLM_PATH, PARSING_PATH
from consultas.domain import Asker
from consultas.models import ChatStore, ConfigStore


@dataclass(frozen=True)
class ApiSettings:
    self_url: str  # base URL of the server that mounts the modules (ServerSettings.self_url)
    embeddings_path: str = EMBEDDINGS_PATH
    llm_path: str = LLM_PATH
    data_path: str = DATA_PATH
    parsing_path: str = PARSING_PATH  # only for the attached documents (POST /parsing/preview)

    def modules(self) -> HttpModules:
        return HttpModules(
            self.self_url, self.embeddings_path, self.llm_path, self.data_path, parsing_path=self.parsing_path
        )


def _settings(request: Request) -> ApiSettings:
    settings: ApiSettings = request.app.state.settings
    return settings


def _modules(request: Request) -> HttpModules:
    modules: HttpModules = request.app.state.modules
    return modules


def _asker(modules: Annotated[HttpModules, Depends(_modules)]) -> Asker:
    return Asker(
        modules.vectors,
        modules.retriever,
        modules.generator,
        modules.chats,
        modules.config,
        modules.previewer,
        modules.vision,
    )


def _chats(modules: Annotated[HttpModules, Depends(_modules)]) -> ChatStore:
    return modules.chats


def _config(modules: Annotated[HttpModules, Depends(_modules)]) -> ConfigStore:
    return modules.config


# Types for route parameters: `def route(asker: Asking) -> ...`.
Settings = Annotated[ApiSettings, Depends(_settings)]
Asking = Annotated[Asker, Depends(_asker)]
Chats = Annotated[ChatStore, Depends(_chats)]
Config = Annotated[ConfigStore, Depends(_config)]
