"""Bodies of the requests and answers (keys in English). A response that already is a consultas.models model (Source,
ChatSummary, ChatDetail) is used as it is. An unknown key is a 422, never ignored."""

from dataclasses import dataclass, field
from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, model_validator

from consultas.config import MAX_ATTACHMENTS, MAX_HISTORY, MAX_K, MAX_LABEL, MAX_PANELS, MAX_PROMPT, MAX_QUESTION
from consultas.models import AttachmentUse, ConfigOrigin, CourseMatch, PanelAnswer, PanelStatus, Source

STRICT = ConfigDict(extra="forbid")
type ServiceState = Literal["ok", "unavailable"]
type QuestionText = Annotated[str, Field(min_length=1, max_length=MAX_QUESTION)]
type K = Annotated[int, Field(ge=1, le=MAX_K)]
type MinScore = Annotated[float, Field(ge=0.0, le=1.0)]
type Prompt = Annotated[str, Field(min_length=1, max_length=MAX_PROMPT)]
type History = Annotated[int, Field(ge=0, le=MAX_HISTORY)]


@dataclass(frozen=True)
class HealthStatus:
    status: Literal["ok", "degraded"]  # ok if embeddings, llm and data answer (parsing only serves attachments)
    version: str
    embeddings: ServiceState
    llm: ServiceState
    data: ServiceState
    parsing: ServiceState  # without it a document can't be attached; the rest works


@dataclass(frozen=True)
class AttachmentBody:
    """A document (pdf, docx, doc) or an image (png, jpg, webp) that searches what is similar to it. It is never
    stored: the question keeps only its name and type."""

    __pydantic_config__ = STRICT

    name: Annotated[str, Field(min_length=1, max_length=255)]
    content: Annotated[str, Field(min_length=1)]  # the file, in base64
    mime: str | None = None  # None: from the extension of `name`


type Attachments = Annotated[list[AttachmentBody], Field(max_length=MAX_ATTACHMENTS)]


@dataclass(frozen=True)
class AgainstBody:
    """Where to search, exactly one: `embeddings_experiment`, the EXP_CHUNK of a finished embeddings experiment (the
    laboratory, feature 053: nothing official is kept), or `embeddings_model`, the official chunks with that model's
    vectors although it isn't the active one (feature 060: an official question)."""

    __pydantic_config__ = STRICT

    embeddings_experiment: Annotated[str, Field(min_length=1)] | None = None
    embeddings_model: Annotated[str, Field(min_length=1)] | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> Self:
        if (self.embeddings_experiment is None) == (self.embeddings_model is None):
            raise ValueError("against takes exactly one of embeddings_experiment and embeddings_model")
        return self


@dataclass(frozen=True)
class LlmBody:
    """Only for this question; what is left out is llm's active configuration (llm says what it admits: 422)."""

    __pydantic_config__ = STRICT

    model: Annotated[str, Field(min_length=1)] | None = None
    temperature: Annotated[float, Field(ge=0.0)] | None = None
    num_ctx: Annotated[int, Field(ge=1)] | None = None
    max_tokens: Annotated[int, Field(ge=1)] | None = None


@dataclass(frozen=True)
class NewSearch:
    """Body of POST /search: the chunks closest to a question, without the LLM."""

    __pydantic_config__ = STRICT

    question: QuestionText | None = None  # it may be left out only with attachments
    k: K | None = None  # None: the active configuration's
    against: AgainstBody | None = None
    attachments: Attachments = field(default_factory=list)


@dataclass(frozen=True)
class NewQuestion:
    """Body of POST /ask. Without `chat`, a new one; with it, the conversation goes on (its last turns go to the LLM).
    With `attachments`, each document and image searches what is similar to it too; `question` may then be left out.
    """

    __pydantic_config__ = STRICT

    question: QuestionText | None = None
    k: K | None = None
    chat: Annotated[str, Field(min_length=1)] | None = None
    llm: LlmBody | None = None
    against: AgainstBody | None = None
    attachments: Attachments = field(default_factory=list)


@dataclass(frozen=True)
class SecondsView:
    search: float
    answer: float


@dataclass(frozen=True)
class AnswerView:
    answer: str
    sources: list[Source]  # what the answer cites, numbered in this order ([1] is the first)
    chat: str
    consulta: str
    model: str | None  # the LLM; None if it wasn't called
    found: bool  # False: nothing passed min_score and the LLM wasn't called
    seconds: SecondsView
    laboratory: bool = False
    attachments: list[AttachmentUse] = field(default_factory=list)  # what each one searched with
    courses: list[CourseMatch] = field(default_factory=list)  # the documents of the courses it named (feature 057)


@dataclass(frozen=True)
class ConfigBody:
    """Body of PUT /config: what is left out takes the default."""

    __pydantic_config__ = STRICT

    k: K | None = None
    min_score: MinScore | None = None
    prompt: Prompt | None = None  # with {context} and {question}
    history: History | None = None


@dataclass(frozen=True)
class ConfigPatch:
    """Body of PATCH /config: only what comes changes."""

    __pydantic_config__ = STRICT

    k: K | None = None
    min_score: MinScore | None = None
    prompt: Prompt | None = None
    history: History | None = None


@dataclass(frozen=True)
class DefaultConfig:
    k: int
    min_score: float
    prompt: str
    history: int


@dataclass(frozen=True)
class ConfigView:
    k: int
    min_score: float
    prompt: str
    history: int
    origin: ConfigOrigin
    modified: str | None
    problem: str | None  # why the stored one isn't used
    default: DefaultConfig


@dataclass(frozen=True)
class PanelBody:
    """A panel of POST /compare: where it searches, with which LLM and how many chunks (what is left out: the active
    configurations)."""

    __pydantic_config__ = STRICT

    label: Annotated[str, Field(min_length=1, max_length=MAX_LABEL)] | None = None  # None: "Panel <n>"
    against: AgainstBody | None = None
    llm: LlmBody | None = None
    k: K | None = None


@dataclass(frozen=True)
class NewComparison:
    """Body of POST /compare: one question (and its attachments) to 1–4 panels, run in order."""

    __pydantic_config__ = STRICT

    panels: Annotated[list[PanelBody], Field(min_length=1, max_length=MAX_PANELS)]
    question: QuestionText | None = None  # it may be left out only with attachments
    attachments: Attachments = field(default_factory=list)


@dataclass(frozen=True)
class PanelView:
    index: int  # its position in `panels`, from 0
    label: str
    against: dict[str, str] | None  # as it was sent
    status: PanelStatus
    error: str | None
    answer: PanelAnswer | None  # /ask's answer without its chat; None if the panel failed


@dataclass(frozen=True)
class ComparisonView:
    comparison: str
    question: str
    created: str
    panels: list[PanelView]
