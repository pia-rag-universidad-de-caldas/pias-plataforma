"""What the domain and the routes ask of the outside, and the errors of each side: Ollama (adapters/ollama_client.py)
and data (adapters/data/)."""

from collections.abc import Callable
from typing import Protocol

from .concepts import ChatAnswer, InstalledModel, LlmConfig
from .requests import SettledChat
from .results import PullProgress


class ModelsDown(Exception):
    """Ollama doesn't answer, or doesn't have the model downloaded: 503 with the reason (never a 500)."""


class InvalidChat(Exception):
    """A model that isn't admitted, a value out of range or images for a model without vision: 422."""


class DataDown(Exception):
    """data (or Neo4j behind it) doesn't answer: 503."""


class DataRefused(Exception):
    """data refused what was sent: 502."""


class LanguageModels(Protocol):
    """Ollama. Every error of its own is ModelsDown, except a 400 for what was sent (InvalidChat)."""

    def version(self) -> str: ...

    def installed(self) -> list[InstalledModel]: ...

    def pull(self, name: str, progress: Callable[[PullProgress], None]) -> None:
        """Downloads it, telling every line of progress; returns when Ollama has it."""
        ...

    def delete(self, name: str) -> bool:
        """False if Ollama didn't have it."""
        ...

    def chat(self, chat: SettledChat) -> ChatAnswer:
        """ModelsDown also if the model isn't downloaded (with the `ollama pull` that fixes it)."""
        ...


class ConfigStore(Protocol):
    def active(self) -> LlmConfig | None:
        """The stored one, as it is (domain/active_config.py decides if it still works); None if none."""
        ...

    def set(self, config: LlmConfig) -> None: ...

    def clear(self) -> bool:
        """False if there was none."""
        ...
