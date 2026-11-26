"""What is asked for: a chat as it comes, and as it goes to Ollama once settled on the active configuration."""

from dataclasses import dataclass

from .concepts import ChatMessage


@dataclass(frozen=True)
class ChatRequest:
    """What isn't sent (None) comes from the active configuration."""

    messages: tuple[ChatMessage, ...]
    model: str | None = None
    temperature: float | None = None
    num_ctx: int | None = None
    max_tokens: int | None = None


@dataclass(frozen=True)
class SettledChat:
    """A chat with every value decided and checked (domain/settle.py): what the Ollama client sends."""

    model: str
    messages: tuple[ChatMessage, ...]
    temperature: float
    num_ctx: int
    max_tokens: int
