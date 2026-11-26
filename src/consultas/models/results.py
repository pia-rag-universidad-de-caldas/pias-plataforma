"""What answering a question gives (POST /ask), what is read back of the stored chats, and (feature 060) where a
question can be asked and what a comparison gives."""

from dataclasses import dataclass, field
from enum import StrEnum

from .concepts import AttachmentUse, CourseMatch, LlmOptions, Source
from .requests import Against
from .stored import QuestionProperties


@dataclass(frozen=True)
class Seconds:
    search: float  # the vector of the question and the search
    answer: float  # the LLM (0 if it wasn't called)


@dataclass(frozen=True)
class Answer:
    answer: str
    sources: list[Source]  # what the answer cites: the chunks over min_score, best first
    chat: str
    consulta: str  # the id of the stored CONSULTA
    model: str | None  # the LLM that answered; None if it wasn't called (nothing found)
    found: bool  # False: no chunk passed min_score and the LLM wasn't called
    seconds: Seconds
    laboratory: bool = False  # asked against an embeddings experiment: nothing official
    attachments: list[AttachmentUse] = field(default_factory=list)  # what each attachment searched with
    courses: list[CourseMatch] = field(default_factory=list)  # the documents it named: only theirs searched (057)


@dataclass(frozen=True)
class Response:
    """An answer before it is stored (Asker.respond): what /ask answers without its chat, and the CONSULTA to keep."""

    answer: str
    sources: list[Source]
    model: str | None
    found: bool
    seconds: Seconds
    laboratory: bool
    attachments: list[AttachmentUse]
    courses: list[CourseMatch]
    stored: QuestionProperties


@dataclass(frozen=True)
class ChatSummary:
    id: str
    title: str
    created: str
    modified: str
    laboratory: bool


@dataclass(frozen=True)
class CitedChunk:
    """A chunk a stored question was answered with (RESPONDIDA_CON)."""

    id: str
    label: str  # FRAGMENTOS or EXP_CHUNK
    score: float
    order: int  # 1 is the best: the number the answer cites it with
    text: str
    headings: list[str]
    pages: list[int]


@dataclass(frozen=True)
class StoredQuestion:
    id: str
    question: str
    answer: str
    llm_model: str | None
    embedding_model: str
    k: int
    created: str
    seconds: float
    laboratory: bool
    embeddings_experiment: str | None
    sources: list[CitedChunk] = field(default_factory=list)
    attachments: list[str] = field(default_factory=list)  # their names: the files themselves are never stored


@dataclass(frozen=True)
class ChatDetail:
    chat: ChatSummary
    questions: list[StoredQuestion]  # oldest first


# Where a question can be asked (feature 060: GET /targets). Field names are the JSON keys.


@dataclass(frozen=True)
class OfficialTarget:
    """The official chunks with one embeddings model."""

    model: str
    dimensions: int
    active: bool  # embeddings' active model: what a question without `against` uses
    documents_done: int  # official documents with its vectors over their current chunks
    documents_total: int


@dataclass(frozen=True)
class ChunkingParameters:
    chunker: str | None
    tokenizer: str | None
    max_tokens: int | None


@dataclass(frozen=True)
class ExperimentTarget:
    """A finished embeddings experiment, with the chunking experiment whose chunks it embedded."""

    embeddings_experiment: str
    name: str
    model: str
    dimensions: int
    chunking_experiment: str | None
    chunking_name: str | None  # None: chunking has no experiment with that id (deleted)
    chunking: ChunkingParameters | None
    documents: int


@dataclass(frozen=True)
class Targets:
    official: list[OfficialTarget]
    experiments: list[ExperimentTarget]


# A comparison (feature 060: POST /compare): one question to up to four panels.


class PanelStatus(StrEnum):
    OK = "ok"  # values of the JSON and of the stored `paneles`
    ERROR = "error"


@dataclass(frozen=True)
class PanelAnswer:
    """A panel's answer: /ask's without the chat (a comparison's CONSULTA has none)."""

    answer: str
    sources: list[Source]
    consulta: str
    model: str | None
    found: bool
    seconds: Seconds
    laboratory: bool
    attachments: list[AttachmentUse] = field(default_factory=list)
    courses: list[CourseMatch] = field(default_factory=list)


@dataclass(frozen=True)
class PanelResult:
    index: int  # its position in the request, from 0
    label: str
    against: Against | None
    llm: LlmOptions
    k: int | None
    status: PanelStatus
    error: str | None = None
    answer: PanelAnswer | None = None


@dataclass(frozen=True)
class Comparison:
    id: str
    question: str
    created: str
    panels: list[PanelResult]


@dataclass(frozen=True)
class ComparisonSummary:
    id: str
    question: str
    created: str
    panels: int  # how many
    models: list[str]  # their LLMs, in order and without repeating
