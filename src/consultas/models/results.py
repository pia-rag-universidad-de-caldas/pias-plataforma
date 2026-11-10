"""What answering a question gives (POST /ask) and what is read back of the stored chats."""

from dataclasses import dataclass, field

from .concepts import AttachmentUse, Source


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
