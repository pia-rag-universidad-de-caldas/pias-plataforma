"""What lives in memory: messages, the configuration, what Ollama has and what it answers."""

from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    """Who says a message, as Ollama (and every chat model) names it."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str
    images: tuple[str, ...] = ()  # base64, only for a vision model


class ConfigOrigin(StrEnum):
    """Where the active configuration came from. The VALUES are stored (CONFIG_OFICIAL.origen): Spanish."""

    DEFAULT = "defecto"
    MANUAL = "manual"


@dataclass(frozen=True)
class LlmConfig:
    """The active configuration (this module's CONFIG_OFICIAL): what a chat uses for what it doesn't send."""

    model: str
    temperature: float
    num_ctx: int  # tokens of context Ollama gives the model
    max_tokens: int  # tokens of an answer (Ollama's num_predict)
    system: str  # system prompt put first when the messages bring none ("" puts nothing)
    origin: ConfigOrigin = ConfigOrigin.DEFAULT
    modified: str | None = None


@dataclass(frozen=True)
class InstalledModel:
    """A model Ollama has downloaded (any, admitted or not)."""

    name: str
    size: int  # bytes
    family: str | None
    modified: str | None  # ISO, as Ollama says it


@dataclass(frozen=True)
class ChatAnswer:
    model: str
    content: str
    prompt_tokens: int  # what the model read (Ollama's prompt_eval_count)
    answer_tokens: int  # what it wrote (eval_count)
    seconds: float  # Ollama's total_duration
