"""What chunking is asked to do: a production run (POST /chunking/runs, feature 023) and an experiment (POST
/chunking/experiments, feature 025: files, conversion and per-section plan; feature 028: page ranges, official JSON and
conversion-only)."""

from dataclasses import dataclass, field

from .concepts import ChunkingStrategy, ConversionParameters, StrategyParameters


@dataclass(frozen=True)
class DocumentFilter:
    """The filters of GET /ingesta/data; all must match at once. Empty = every chunkable file."""

    types: list[str] = field(default_factory=list)  # extensions (pdf, docx...)
    year: int | None = None
    month: int | None = None
    week: str | None = None  # as the folder: Semana_04
    code: str | None = None


@dataclass(frozen=True)
class RunRequest:
    simulate: bool = False  # only count what would be processed: nothing is converted nor written
    filter: DocumentFilter = field(default_factory=DocumentFilter)  # ignored when `sha256s` is given
    limit: int | None = None  # at most this many documents processed (or counted, with simulate)
    retry_errors: bool = False  # documents in error with the same parameters are retried
    sha256s: list[str] = field(default_factory=list)  # exactly these documents, even if already chunked (reprocessing)


@dataclass(frozen=True)
class RequestedStrategy:
    """A strategy as asked for; None = not asked (its default, if the strategy uses it)."""

    strategy: ChunkingStrategy | None = None
    tokenizer: str | None = None
    max_tokens: int | None = None
    merge_peers: bool | None = None
    overlap_tokens: int | None = None
    embedding_model: str | None = None
    similarity_threshold: float | None = None


@dataclass(frozen=True)
class PositionRange:
    """A stretch of the document, over its sections in order: 0 = start, 1 = end (first 20 % = 0 to 0.2)."""

    start: float
    end: float


@dataclass(frozen=True)
class Match:
    """When a rule takes a section: its title contains one of `titles` (case and accent insensitive) and/or it falls
    in `position`; both, if both are given."""

    titles: list[str] = field(default_factory=list)
    position: PositionRange | None = None


@dataclass(frozen=True)
class Rule:
    match: Match
    chunking: StrategyParameters


@dataclass(frozen=True)
class Plan:
    """Rules in order (the first one that matches a section wins) and the strategy of the sections none takes."""

    rules: list[Rule]
    default: StrategyParameters


@dataclass(frozen=True)
class PageRange:
    """Pages `first` to `last` (1-based, both included) of a paginated listing (feature 028)."""

    first: int
    last: int


@dataclass(frozen=True)
class JsonSelection:
    """Official JSON nodes (feature 028), exactly one way: `all`, the pages `pages` of `per_page`, or `sha256s`."""

    all: bool = False
    pages: PageRange | None = None
    per_page: int | None = None
    sha256s: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FileSelection:
    """Exactly one way: `sha256s`; ingesta's filters with `limit`, with `all` (every match) or with `pages` of
    `per_page`; the documents of `from_experiment`; or official JSON nodes with `from_json` (feature 028)."""

    sha256s: list[str] = field(default_factory=list)
    filter: DocumentFilter | None = None
    limit: int | None = None
    from_experiment: str | None = None
    all: bool = False
    pages: PageRange | None = None
    per_page: int | None = None
    from_json: JsonSelection | None = None


@dataclass(frozen=True)
class ExperimentRequest:
    name: str
    description: str
    files: FileSelection
    conversion: ConversionParameters  # ignored with `files.from_json`: each JSON keeps the one it was promoted with
    plan: Plan | None  # None = only convert (feature 028): no sections nor chunks
