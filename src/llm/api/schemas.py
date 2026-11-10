"""Bodies of the requests and answers (keys in English; the shapes are those of the contract with consultas and the
pipeline, spec/features/048-consultas-rag/contratos.md). A response that already is a llm.models model (ModelPull) is
used as it is. An unknown key is a 422, never ignored. The ranges are checked by the domain (domain/validation.py),
which knows each model's context."""

from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from llm.models import ConfigOrigin

STRICT = ConfigDict(extra="forbid")
type ServiceState = Literal["ok", "unavailable"]
type ModelName = Annotated[str, Field(min_length=1, max_length=200)]


@dataclass(frozen=True)
class HealthStatus:
    status: Literal["ok", "degraded"]  # ok if Ollama and data answer
    version: str
    ollama: ServiceState
    ollama_version: str | None
    ollama_url: str
    data: ServiceState


@dataclass(frozen=True)
class AdmittedModel:
    """A model of config.MODELS."""

    name: str
    context: int  # the most num_ctx it admits
    vision: bool  # whether a message may carry images
    installed: bool  # whether Ollama has it downloaded
    default: bool  # the one of the default configuration


@dataclass(frozen=True)
class InstalledView:
    """A model Ollama has (admitted or not)."""

    name: str
    size: int  # bytes
    family: str | None
    modified: str | None


@dataclass(frozen=True)
class ModelsView:
    admitted: list[AdmittedModel]
    installed: list[InstalledView]


@dataclass(frozen=True)
class NewPull:
    __pydantic_config__ = STRICT

    name: ModelName  # one of the admitted models


@dataclass(frozen=True)
class ConfigBody:
    """Body of PUT /config: what is left out takes the default (num_ctx: the model's)."""

    __pydantic_config__ = STRICT

    model: ModelName
    temperature: float | None = None
    num_ctx: int | None = None
    max_tokens: int | None = None
    system: str | None = None


@dataclass(frozen=True)
class ConfigPatch:
    """Body of PATCH /config: only what comes changes."""

    __pydantic_config__ = STRICT

    model: ModelName | None = None
    temperature: float | None = None
    num_ctx: int | None = None
    max_tokens: int | None = None
    system: str | None = None  # "" removes it


@dataclass(frozen=True)
class DefaultConfig:
    model: str
    temperature: float
    num_ctx: int
    max_tokens: int
    system: str


@dataclass(frozen=True)
class ConfigView:
    model: str
    temperature: float
    num_ctx: int
    max_tokens: int
    system: str
    origin: ConfigOrigin
    modified: str | None
    default: DefaultConfig


@dataclass(frozen=True)
class MessageBody:
    __pydantic_config__ = STRICT

    role: Literal["system", "user", "assistant"]
    content: str
    images: list[str] | None = None  # base64, only for a vision model


@dataclass(frozen=True)
class NewChat:
    """Body of POST /chat: what isn't sent comes from the active configuration."""

    __pydantic_config__ = STRICT

    messages: Annotated[list[MessageBody], Field(min_length=1)]
    model: ModelName | None = None
    temperature: float | None = None
    num_ctx: int | None = None
    max_tokens: int | None = None


@dataclass(frozen=True)
class AnswerMessage:
    role: Literal["assistant"]
    content: str


@dataclass(frozen=True)
class ChatView:
    model: str
    message: AnswerMessage
    prompt_tokens: int
    answer_tokens: int
    seconds: float
