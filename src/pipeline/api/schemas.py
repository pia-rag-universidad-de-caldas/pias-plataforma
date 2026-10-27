"""Bodies of the pipeline's routes. Keys in English (like chunking and data); unknown keys are a 422. Free-form parts
(stages, files, params, artifacts) are JSON, checked by the domain with messages that say where."""

from dataclasses import dataclass, field
from typing import Literal

from pydantic import ConfigDict

from pipeline.config import TEMPLATE
from pipeline.models import JsonObject, JsonValue

STRICT = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class Error:
    detail: str


type Responses = dict[int | str, dict[str, object]]


def error(code: int, description: str) -> Responses:
    """One `responses=` entry of a route: {"detail"} body with its description."""
    return {code: {"model": Error, "description": description}}


# --- requests ---


@dataclass(frozen=True)
class NewTemplate:
    """`stages`: [{id, action, params?, actor?, stages? (a cycle's), max_iterations?, needs?/gives? (external)}]."""

    __pydantic_config__ = STRICT

    id: str
    stages: list[JsonObject]
    name: str = ""
    description: str = ""


@dataclass(frozen=True)
class TemplateChange:
    __pydantic_config__ = STRICT

    stages: list[JsonObject]
    name: str = ""
    description: str = ""


@dataclass(frozen=True)
class OrderBody:
    __pydantic_config__ = STRICT

    order: list[str]


@dataclass(frozen=True)
class MoveBody:
    __pydantic_config__ = STRICT

    before: str | None = None
    after: str | None = None


@dataclass(frozen=True)
class NewRun:
    """`files`: {all, types...} | {pages: {from, to}, per_page, types...} | {sha256s} | {from_run}. `params`: stage
    id → params over the template's (a cycle's go to every iteration: {"conversion": {...}} or {"plan": {...}})."""

    __pydantic_config__ = STRICT

    template: str = TEMPLATE
    name: str = ""
    files: JsonObject | None = None
    params: dict[str, JsonObject] = field(default_factory=dict)
    simulate: bool = False


@dataclass(frozen=True)
class DecisionBody:
    """`score` goes as is to POST /chunking/experiments/{id}/scores of the iteration's experiment
    ({author, criteria, comment}); `next` (retry only) is merged over the last iteration's configuration."""

    __pydantic_config__ = STRICT

    decision: Literal["approve", "retry"]
    actor: str | None = None
    iteration: int | None = None
    next: JsonObject = field(default_factory=dict)
    score: JsonObject | None = None


@dataclass(frozen=True)
class CompleteBody:
    __pydantic_config__ = STRICT

    actor: str | None = None
    result: JsonValue = None
    error: str | None = None


@dataclass(frozen=True)
class EventBody:
    __pydantic_config__ = STRICT

    actor: str
    kind: str
    detail: JsonValue = None


@dataclass(frozen=True)
class ActorBody:
    __pydantic_config__ = STRICT

    callback_url: str | None = None


# --- answers ---


@dataclass(frozen=True)
class ActionView:
    name: str
    kind: str
    module: str | None
    needs: list[str]
    gives: list[str]
    description: str
    parameters: str


@dataclass(frozen=True)
class TemplateView:
    id: str
    name: str
    description: str
    builtin: bool
    created: str
    modified: str
    stages: list[JsonValue]


@dataclass(frozen=True)
class RunSummary:
    id: str
    name: str
    template: str
    status: str
    created: str
    finished: str | None
    stage: str | None  # the stage at the cursor
    waiting: JsonValue  # {stage, step, actor, since, iteration, exhausted} while waiting


@dataclass(frozen=True)
class RunView:
    id: str
    name: str
    status: str
    created: str
    started: str | None
    finished: str | None
    error: str | None
    stage: str | None
    waiting: JsonValue
    template: JsonValue  # the copy the run took
    files: JsonValue
    params: JsonValue
    cursor: JsonValue
    artifacts: JsonValue
    iterations: list[JsonValue]
    records: list[JsonValue]
    events: list[JsonValue]


@dataclass(frozen=True)
class RunStarted:
    """Answer of POST /runs: the run (202), or with simulate (200) the batch its first selection would take."""

    status: str
    run: RunView | None
    batch: list[str]


@dataclass(frozen=True)
class ActorView:
    name: str
    callback_url: str | None


@dataclass(frozen=True)
class PipelineHealth:
    status: str  # "ok" if ingesta, chunking and data answer; "degraded" otherwise
    version: str
    modules: dict[str, str]  # module → "ok" | "unavailable"
