"""What is asked of the pipeline: which files enter a run, and the actors' answers."""

from dataclasses import dataclass, field
from enum import StrEnum

from .concepts import JsonObject, JsonValue


@dataclass(frozen=True)
class PageRange:
    """Pages `start`..`end` (both included, from 1) of /ingesta/data or /data/nodes/JSON."""

    start: int
    end: int


@dataclass(frozen=True)
class Selection:
    """Exactly one way: `all`, `pages` (with `per_page`), `sha256s` or `from_run` (the batch of another run). The
    filters (`types`, `year`, `month`, `week`, `code`) go with `all` and `pages`, and only on ingesta's files."""

    all: bool = False
    pages: PageRange | None = None
    per_page: int | None = None
    sha256s: tuple[str, ...] = ()
    from_run: str | None = None
    types: tuple[str, ...] = ()
    year: int | None = None
    month: int | None = None
    week: str | None = None
    code: str | None = None

    @property
    def filtered(self) -> bool:
        return bool(self.types) or any(v is not None for v in (self.year, self.month, self.week, self.code))


@dataclass(frozen=True)
class RunRequest:
    template: str
    name: str
    files: Selection | None  # for the selections of ingesta (and of JSON, when their stage doesn't say)
    params: dict[str, JsonObject] = field(default_factory=dict)  # stage id → params over the template's


class DecisionKind(StrEnum):
    APPROVE = "approve"
    RETRY = "retry"


@dataclass(frozen=True)
class Decision:
    """The answer of a cycle's actor. `retry` repeats the cycle with the last configuration plus `next`; `approve`
    closes it with `iteration` (the last one by default). `score` goes to the iteration's experiment."""

    kind: DecisionKind
    actor: str | None = None
    iteration: int | None = None
    next: JsonObject = field(default_factory=dict)
    score: JsonObject | None = None


@dataclass(frozen=True)
class Completion:
    """The answer of an `external` stage: its result, or the error that fails the run."""

    actor: str | None = None
    result: JsonValue = None
    error: str | None = None


@dataclass(frozen=True)
class EventRequest:
    actor: str
    kind: str
    detail: JsonValue = None
