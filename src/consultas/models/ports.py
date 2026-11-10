"""What the domain asks of the other modules, and the errors of each side. Everything is implemented over HTTP
(adapters/): embeddings, llm, data and, for the attachments, parsing."""

from collections.abc import Sequence
from typing import ClassVar, Protocol

from .batch import GraphBatch
from .concepts import (
    ConsultasConfig,
    EmbeddingsExperiment,
    LlmModel,
    LlmOptions,
    Message,
    PreviewedDocument,
    QuestionVector,
    Reply,
    Source,
    TextVectors,
    Turn,
)
from .results import ChatDetail, ChatSummary


class ConsultasError(Exception):
    """Any error of consultas: each subclass is one HTTP status (api/app.py)."""


class ModuleDown(ConsultasError):
    """A module (or what is behind it: the model, Ollama, Neo4j) doesn't answer: 503 saying which. Nothing is stored."""

    service: ClassVar[str] = "a module"

    def __init__(self, message: str) -> None:
        super().__init__(f"{self.service} is not answering: {message}")


class EmbeddingsDown(ModuleDown):
    service = "embeddings"


class LlmDown(ModuleDown):
    service = "llm"


class DataDown(ModuleDown):
    service = "data"


class ParsingDown(ModuleDown):
    service = "parsing"


class NoVisionModel(ConsultasError):
    """An image came, and llm has no vision model downloaded to describe it: 503, saying how to get one."""


class InvalidQuestion(ConsultasError):
    """What was asked can't be done (a model llm doesn't admit, a prompt without {context}...): 422."""


class Rejected(ConsultasError):
    """A module refused what consultas sent it (a bug, not the user's): 502."""


class NotFound(ConsultasError):
    """No chat, or no embeddings experiment, with that id: 404."""


class Conflict(ConsultasError):
    """The embeddings experiment didn't finish, or the chat is of the other kind (official, laboratory): 409."""


class Vectors(Protocol):
    """embeddings."""

    def question(self, text: str, model: str | None = None, max_tokens: int | None = None) -> QuestionVector:
        """With the active configuration's model, or with `model` (an experiment's)."""
        ...

    def texts(self, texts: Sequence[str], model: str, max_tokens: int) -> TextVectors:
        """One vector per text, in order, with that model and limit (a longer text is cut, never fails)."""
        ...

    def experiment(self, id: str) -> EmbeddingsExperiment | None:
        """None if embeddings has no experiment with that id."""
        ...


class Previewer(Protocol):
    """parsing: a document read without storing it (POST /parsing/preview)."""

    def preview(self, name: str, mime: str, content: bytes) -> PreviewedDocument:
        """InvalidQuestion if parsing can't read it (not a document, corrupt...), ParsingDown if it doesn't answer."""
        ...


class Vision(Protocol):
    """What llm says of its models, to describe an image."""

    def models(self) -> list[LlmModel]:
        """The admitted ones, with whether each one sees images and is downloaded."""
        ...

    def active_model(self) -> str:
        """The model of llm's active configuration: the one that answers if the question doesn't say another."""
        ...


class Retriever(Protocol):
    """data's search."""

    def search(self, index: str, vector: list[float], k: int, experiment: str | None = None) -> list[Source]:
        """Best first; nothing if the index doesn't exist (nothing was embedded with that model yet)."""
        ...


class Generator(Protocol):
    """llm."""

    def chat(self, messages: Sequence[Message], options: LlmOptions) -> Reply: ...


class ChatStore(Protocol):
    """The chats and their questions, in data."""

    def chat(self, id: str) -> ChatSummary | None: ...

    def history(self, id: str, turns: int) -> list[Turn]:
        """The last `turns` questions of the chat with their answers, oldest first."""
        ...

    def save(self, batch: GraphBatch) -> None:
        """All of it or nothing."""
        ...

    def chats(self) -> list[ChatSummary]:
        """The most recently modified first."""
        ...

    def detail(self, id: str) -> ChatDetail | None: ...

    def delete(self, id: str) -> bool:
        """The chat and its questions (not the chunks they cite); False if there was none."""
        ...


class ConfigStore(Protocol):
    def active(self) -> ConsultasConfig | None:
        """The stored one; None if nobody set one (or it can't be read)."""
        ...

    def set(self, config: ConsultasConfig) -> None: ...

    def clear(self) -> bool:
        """False if there was none."""
        ...
