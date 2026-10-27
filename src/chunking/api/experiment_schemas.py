"""Bodies of the experiment and score routes (feature 025). Keys in English, like the rest of chunking; unknown keys
are a 422 (a typo in a parameter name must not be silently ignored)."""

from dataclasses import dataclass, field
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from chunking.config import (
    HEADING_LEVEL,
    MAX_TOKENS_RANGE,
    NUMBERED_TITLES,
    SELECTION_MAX_PER_PAGE,
    TABLE_MODE,
    TABLE_STRUCTURE,
)
from chunking.models import (
    ChunkingStrategy,
    ExperimentDocument,
    ExperimentProgress,
    ExperimentStatus,
    KeyResults,
    PromotionKind,
    Score,
    ScoreSummary,
    TableMode,
)

from .schemas import Sha256

STRICT = ConfigDict(extra="forbid")
DEFAULT_TABLE_MODE = TableMode(TABLE_MODE)


@dataclass(frozen=True)
class PagesBody:
    """Pages `from` to `to` (1-based, both included) of a paginated listing (feature 028)."""

    __pydantic_config__ = STRICT

    first: Annotated[int, Field(alias="from", ge=1)]
    last: Annotated[int, Field(alias="to", ge=1)]


PerPage = Annotated[int | None, Field(ge=1, le=SELECTION_MAX_PER_PAGE)]


@dataclass(frozen=True)
class JsonFilesBody:
    """Official JSON nodes (feature 028), exactly one way: `all`, `pages` with `per_page`, or `sha256s`."""

    __pydantic_config__ = STRICT

    all: bool = False
    pages: PagesBody | None = None
    per_page: PerPage = None
    sha256s: list[Sha256] = field(default_factory=list)


@dataclass(frozen=True)
class FilesBody:
    """Exactly one way: `sha256s`; ingesta's filters with `limit`, `all` or `pages` + `per_page`; `from_experiment`;
    or `from_json` (official JSON, feature 028)."""

    __pydantic_config__ = STRICT

    sha256s: list[Sha256] = field(default_factory=list)
    limit: Annotated[int | None, Field(ge=1)] = None
    all: bool = False
    pages: PagesBody | None = None
    per_page: PerPage = None
    types: list[str] = field(default_factory=list)
    year: int | None = None
    month: Annotated[int | None, Field(ge=1, le=12)] = None
    week: str | None = None
    code: str | None = None
    from_experiment: str | None = None
    from_json: JsonFilesBody | None = None


@dataclass(frozen=True)
class IncludeBody:
    __pydantic_config__ = STRICT

    tables: bool = True
    lists: bool = True
    page_headers: bool = False
    page_footers: bool = False
    pictures: bool = False


@dataclass(frozen=True)
class ConversionBody:
    __pydantic_config__ = STRICT

    heading_level: Annotated[int, Field(ge=1, le=6)] = HEADING_LEVEL
    numbered_titles: bool = NUMBERED_TITLES  # Roman-numbered list items ("I.", "III.1.") are titles
    table_structure: bool = TABLE_STRUCTURE
    table_mode: TableMode = DEFAULT_TABLE_MODE
    include: IncludeBody = field(default_factory=IncludeBody)


@dataclass(frozen=True)
class StrategyBody:
    """A strategy and its parameters; each left out takes its default if the strategy uses it, and one it doesn't use
    is a 422."""

    __pydantic_config__ = STRICT

    strategy: ChunkingStrategy | None = None  # hybrid (default), element, section, page, fixed, points, semantic
    tokenizer: str | None = None
    max_tokens: Annotated[int | None, Field(ge=MAX_TOKENS_RANGE[0], le=MAX_TOKENS_RANGE[1])] = None
    merge_peers: bool | None = None  # hybrid
    overlap_tokens: Annotated[int | None, Field(ge=0)] = None  # fixed
    embedding_model: str | None = None  # semantic
    similarity_threshold: Annotated[float | None, Field(ge=0, le=1)] = None  # semantic


@dataclass(frozen=True)
class PositionBody:
    """A stretch of the document over its sections: {"from": 0, "to": 0.2} = the first 20 %."""

    __pydantic_config__ = STRICT

    start: Annotated[float, Field(alias="from", ge=0, le=1)]
    end: Annotated[float, Field(alias="to", ge=0, le=1)]


@dataclass(frozen=True)
class MatchBody:
    __pydantic_config__ = STRICT

    titles: list[str] = field(default_factory=list)  # the section title contains one (case/accent insensitive)
    position: PositionBody | None = None


@dataclass(frozen=True)
class RuleBody:
    __pydantic_config__ = STRICT

    match: MatchBody
    chunking: StrategyBody


@dataclass(frozen=True)
class PlanBody:
    __pydantic_config__ = STRICT

    rules: list[RuleBody] = field(default_factory=list)  # in order: the first that matches a section wins
    default: StrategyBody = field(default_factory=StrategyBody)


@dataclass(frozen=True)
class NewExperiment:
    __pydantic_config__ = STRICT

    name: Annotated[str, Field(min_length=1)]
    files: FilesBody
    description: str = ""
    conversion: ConversionBody | None = None  # Docling's defaults; not with files.from_json (each JSON keeps its own)
    plan: PlanBody | None = None  # None = only convert (feature 028); required with files.from_json
    simulate: bool = False  # only which files would enter and which conversions would be reused


@dataclass(frozen=True)
class PreviewFile:
    sha256: str
    origin: str
    name: str
    reused: bool  # its conversion already exists: no Docling


@dataclass(frozen=True)
class FileProblem:
    error: str
    origin: str | None
    sha256: str | None


@dataclass(frozen=True)
class ExperimentStarted:
    """Answer of POST /experiments: the experiment (None with simulate) and its files."""

    id: str | None
    status: ExperimentStatus | Literal["simulated"]
    files: list[PreviewFile]
    to_convert: int
    reused: int
    failures: list[FileProblem]


@dataclass(frozen=True)
class ExperimentSummary:
    id: str
    name: str
    description: str
    status: ExperimentStatus
    created: str
    finished: str | None
    progress: ExperimentProgress


@dataclass(frozen=True)
class ExperimentView:
    id: str
    name: str
    description: str
    status: ExperimentStatus
    created: str
    finished: str | None
    progress: ExperimentProgress
    files: JsonValue  # the request, with every default resolved
    conversion: JsonValue
    plan: JsonValue
    results: JsonValue  # the record of results (None while it runs)
    error: str | None


@dataclass(frozen=True)
class SectionView:
    index: int
    title: str
    level: int
    pages: list[int]
    rule: str  # index of the rule that took it, or "default"
    strategy: str
    parameters: JsonValue
    chunks: int
    tokens: int


@dataclass(frozen=True)
class DocumentView:
    document: ExperimentDocument
    conversion: JsonValue  # the parameters of its conversion
    content: JsonValue  # the converted JSON (by main titles)
    sections: list[SectionView]


@dataclass(frozen=True)
class ChunkView:
    section: int
    index: int  # within its section
    text: str
    headings: list[str]
    pages: list[int]
    tokens: int


# Scores


@dataclass(frozen=True)
class NewScore:
    """Body of POST (and PUT) /experiments/{id}/scores[/{score_id}]. Free criteria: name → SCORE_MIN–SCORE_MAX."""

    __pydantic_config__ = STRICT

    criteria: dict[str, float] = field(default_factory=dict)
    author: str | None = None
    comment: str | None = None


class ScorePatch(BaseModel):
    """Body of PATCH: only the fields sent change; a criterion set to null is removed."""

    model_config = STRICT

    criteria: dict[str, float | None] | None = None
    author: str | None = None
    comment: str | None = None


@dataclass(frozen=True)
class ExperimentScores:
    experiment: str
    scores: list[Score]
    summary: ScoreSummary


@dataclass(frozen=True)
class ComparedView:
    id: str
    name: str
    status: ExperimentStatus
    conversion: JsonValue
    plan: JsonValue
    scores: list[Score]
    summary: ScoreSummary
    results: KeyResults | None


# Promotion (feature 028)


@dataclass(frozen=True)
class PromotionFailure:
    sha256: str
    error: str


@dataclass(frozen=True)
class PromotionView:
    """Answer of POST /experiments/{id}/promote."""

    experiment: str
    kind: PromotionKind
    promoted: int
    failed: list[PromotionFailure]
