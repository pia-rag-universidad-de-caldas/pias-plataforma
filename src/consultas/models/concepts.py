"""What lives in memory while a question is answered: the chunks found, the vector of the question, the messages to the
LLM and its reply, and the active configuration."""

from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True)
class Source:
    """A chunk found for a question: a FRAGMENTOS (official) or an EXP_CHUNK (of an embeddings experiment)."""

    id: str
    score: float  # cosine similarity
    text: str
    headings: list[str]
    pages: list[int]
    sha256: str
    origin: str | None  # the file in the corpus (from its RAW)
    code: str | None  # its PIAA
    activity: str | None = None  # the course it is about, as embeddings read it from the header (feature 057)


@dataclass(frozen=True)
class CourseMatch:
    """A document whose course data's full-text search matched with a question (feature 057)."""

    sha256: str
    name: str | None  # the course's name (actividad)
    activity_code: str | None  # its code (codigo_actividad): 0100105, G6K0346...
    score: float  # Lucene's: only comparable within one search
    origin: str | None = None


@dataclass(frozen=True)
class QuestionVector:
    """The question as embeddings turned it into a vector, and the indexes of the model that did it."""

    model: str
    max_tokens: int
    dimensions: int
    index: str  # FRAGMENTOS
    experiment_index: str  # EXP_CHUNK
    vector: list[float]


@dataclass(frozen=True)
class EmbeddingsExperiment:
    """An embeddings experiment to ask (the laboratory): its state and the model its vectors were calculated with."""

    id: str
    status: str
    model: str
    max_tokens: int


class Role(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True)
class Message:
    role: Role
    content: str
    images: tuple[str, ...] = ()  # base64, only to a vision model


@dataclass(frozen=True)
class TextVectors:
    """Several texts as embeddings turned them into vectors (POST /embeddings/vectors), in their order."""

    model: str
    max_tokens: int
    dimensions: int
    index: str
    experiment_index: str
    vectors: list[list[float]]


class AttachmentKind(StrEnum):
    DOCUMENT = "documento"  # values stored in the CONSULTA (`tipos_adjuntos` says the MIME type)
    IMAGE = "imagen"


@dataclass(frozen=True)
class Attachment:
    """A file that comes with a question (feature 048, phase 2): it searches, it is never stored."""

    name: str
    mime: str
    content: bytes


@dataclass(frozen=True)
class PreviewSection:
    headings: list[str]
    text: str


@dataclass(frozen=True)
class PreviewedDocument:
    """A document as POST /parsing/preview read it: nothing of it is in data."""

    name: str
    pages: int
    truncated: bool
    sections: list[PreviewSection]


@dataclass(frozen=True)
class LlmModel:
    """A model llm admits (GET /llm/models)."""

    name: str
    vision: bool
    installed: bool


@dataclass(frozen=True)
class AttachmentUse:
    """What an attachment gave to the search: how many pieces, how many characters, and an image's description."""

    name: str
    mime: str
    kind: AttachmentKind
    pieces: int  # texts it searched with
    characters: int  # of those texts
    truncated: bool = False  # a document read only in part (its first pages, or a sample of its pieces)
    description: str | None = None  # of an image: what the vision model saw


@dataclass(frozen=True)
class LlmOptions:
    """What changes the LLM only for one question; None: llm's active configuration."""

    model: str | None = None
    temperature: float | None = None
    num_ctx: int | None = None
    max_tokens: int | None = None


@dataclass(frozen=True)
class Reply:
    """What the LLM answered (POST /llm/chat)."""

    model: str
    content: str
    prompt_tokens: int | None = None
    answer_tokens: int | None = None
    seconds: float | None = None


@dataclass(frozen=True)
class Turn:
    """A previous question of the chat and its answer: what goes to the LLM as history."""

    question: str
    answer: str


class ConfigOrigin(StrEnum):
    DEFAULT = "defecto"  # nobody set one: config.py's values
    MANUAL = "manual"  # PUT or PATCH /config


@dataclass(frozen=True)
class ConsultasConfig:
    k: int
    min_score: float
    prompt: str  # with {context} and {question}
    history: int  # previous turns that go to the LLM
    origin: ConfigOrigin = ConfigOrigin.DEFAULT
    modified: str | None = None


@dataclass(frozen=True)
class PreparedAttachment:
    """An attachment read once (feature 060: every panel of a comparison reuses it): a document as parsing read it, or
    what the vision model saw in an image. Its pieces are cut later, to the limit of each embeddings model."""

    attachment: Attachment
    kind: AttachmentKind
    document: PreviewedDocument | None = None
    description: str | None = None


@dataclass(frozen=True)
class Prepared:
    """The attachments of a question, read; `models`: what llm said of its models (asked only with an image)."""

    items: tuple[PreparedAttachment, ...] = ()
    models: tuple[LlmModel, ...] = ()


# What can be asked (feature 060: GET /targets and the checks of a comparison).


@dataclass(frozen=True)
class EmbeddingModel:
    """A model embeddings serves (GET /embeddings/models)."""

    name: str
    dimensions: int
    vector_property: str  # embedding_<model>_<dim>: what data counts its official documents by


@dataclass(frozen=True)
class EmbeddingsRun:
    """An embeddings experiment as GET /embeddings/experiments lists it."""

    id: str
    name: str
    status: str
    model: str
    dimensions: int | None  # None: embeddings doesn't say it (before 059): the model's
    chunking_experiment: str | None
    documents: int  # with its vectors


@dataclass(frozen=True)
class ChunkingExperiment:
    """A chunking experiment (GET /chunking/experiments/{id}): its name and what it chunked with."""

    id: str
    name: str
    chunker: str | None
    tokenizer: str | None
    max_tokens: int | None  # None with a chunker that doesn't use it


@dataclass(frozen=True)
class Coverage:
    """How many official documents have a model's vectors (GET /data/progress/embeddings)."""

    done: int
    total: int
