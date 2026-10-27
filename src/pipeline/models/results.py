"""A run of a pipeline and what it records: where it is, its cycle iterations, its stages and its events."""

from dataclasses import dataclass, field
from enum import StrEnum

from .concepts import JsonObject, JsonValue, Template
from .requests import Selection


class RunStatus(StrEnum):
    """The VALUES are stored (PIPE_CORRIDA.estado), except INTERRUPTED: a `queued`/`running` run this server isn't
    processing (it stopped in the middle)."""

    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


FINAL = frozenset({RunStatus.DONE, RunStatus.CANCELLED})


class IterationStatus(StrEnum):
    RUNNING = "running"  # its stages are running or waiting for the score
    RETRIED = "retried"  # its actor asked for another one
    APPROVED = "approved"
    DISCARDED = "discarded"  # another one of the cycle was approved, or the run was cancelled


@dataclass(frozen=True)
class Cursor:
    """The stage a run is at: `stage` in the template and, inside a cycle, `step` in its stages."""

    stage: int
    step: int | None = None


@dataclass(frozen=True)
class Iteration:
    stage: str  # the cycle
    index: int  # from 1
    config: JsonObject  # what its stages read over their own params
    started: str
    status: IterationStatus = IterationStatus.RUNNING
    artifacts: JsonObject = field(default_factory=dict)
    experiments: tuple[str, ...] = ()  # chunking experiments made in it
    score: JsonObject | None = None
    finished: str | None = None


@dataclass(frozen=True)
class StageRecord:
    stage: str
    status: str  # "done" or "failed"
    started: str
    finished: str
    iteration: int | None = None
    result: JsonValue = None
    error: str | None = None


@dataclass(frozen=True)
class Event:
    index: int
    actor: str
    kind: str
    detail: JsonValue
    created: str


@dataclass(frozen=True)
class Waiting:
    """What a waiting run waits for: `step` (a review or an external stage) of `stage` (its cycle, or itself)."""

    stage: str
    step: str
    actor: str
    since: str
    iteration: int | None = None
    exhausted: bool = False  # the cycle reached max_iterations: only approve or cancel


@dataclass(frozen=True)
class PipelineRun:
    id: str
    name: str
    template: Template  # a copy taken when the run was created: changing the template doesn't change the run
    status: RunStatus
    created: str
    files: Selection | None = None
    params: dict[str, JsonObject] = field(default_factory=dict)
    cursor: Cursor = Cursor(0)
    artifacts: JsonObject = field(default_factory=dict)  # those outside cycles and the approved ones
    iterations: tuple[Iteration, ...] = ()
    records: tuple[StageRecord, ...] = ()
    events: tuple[Event, ...] = ()
    waiting: Waiting | None = None
    started: str | None = None  # when the stage at the cursor started
    finished: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class InboxItem:
    """A stage waiting for an actor: what the inbox lists and what is POSTed to its callback_url."""

    run: str
    name: str
    stage: str
    step: str
    actor: str
    since: str
    iteration: int | None
    exhausted: bool
    experiment: str | None  # the chunking experiment to look at (GET /chunking/experiments/{id})
    batch: list[str]  # the sha256s the stage works on
    artifacts: JsonObject
    answer: str  # the route to answer to
