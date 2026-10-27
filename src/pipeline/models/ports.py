"""What the pipeline's domain needs from the outside (implemented in adapters/, over HTTP) and its errors."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from .concepts import Actor, JsonObject, JsonValue, Stage, StageKind, Template
from .requests import Selection
from .results import PipelineRun


class PipelineError(Exception):
    """Base of the pipeline's errors."""


class UnavailableError(PipelineError):
    """A module (or Neo4j behind data) didn't answer: 503."""


class RejectedError(PipelineError):
    """A module refused what the pipeline sent: 502 (the pipeline asked wrong)."""


class ActionError(PipelineError):
    """A stage couldn't do its work (an experiment failed, nothing was promoted...): the run fails."""


class InvalidTemplate(PipelineError):
    """A template, or an order of its stages, that can't run: 422."""


class InvalidRequest(PipelineError):
    """A malformed selection, decision or parameter: 422."""


class ConflictError(PipelineError):
    """What was asked doesn't fit the run's state (an answer to a stage that isn't waiting for it...): 409."""


class NotFoundError(PipelineError):
    """A template, run or experiment that doesn't exist: 404."""


@dataclass(frozen=True)
class SourcePage:
    """One page of ingesta's chunkable files."""

    sha256s: tuple[str, ...]
    pages: int
    reorganized: str | None  # `reorganizado`: if it changes between two pages, the pages may have shifted


@dataclass(frozen=True)
class IdPage:
    ids: tuple[str, ...]
    pages: int


@dataclass(frozen=True)
class ExperimentOutcome:
    id: str
    status: str  # chunking's ExperimentStatus: "finished", "failed"...
    error: str | None = None


@dataclass(frozen=True)
class Promotion:
    """What a promotion wrote: the sha256s promoted (None if chunking only gave their number) and the failures."""

    count: int
    promoted: tuple[str, ...] | None = None
    failed: tuple[tuple[str, str], ...] = ()  # (sha256, error)


class IngestaPort(ABC):
    @abstractmethod
    def page(self, selection: Selection, page: int, per_page: int) -> SourcePage: ...

    @abstractmethod
    def has(self, sha256: str) -> bool:
        """Whether a chunkable file has that content."""


class ChunkingPort(ABC):
    @abstractmethod
    def run_experiment(self, body: JsonObject) -> ExperimentOutcome:
        """Starts the experiment (waiting its turn while chunking is busy) and waits until it ends."""

    @abstractmethod
    def score(self, experiment: str, score: JsonObject) -> None: ...

    @abstractmethod
    def promote(self, experiment: str) -> Promotion: ...


class DataPort(ABC):
    @abstractmethod
    def json_page(self, page: int, per_page: int) -> IdPage:
        """One page of the official JSON nodes."""


class RunStore(ABC):
    """Where templates and runs are kept (the graph, through data)."""

    @abstractmethod
    def templates(self) -> list[Template]: ...

    @abstractmethod
    def template(self, id: str) -> Template | None: ...

    @abstractmethod
    def save_template(self, template: Template) -> None: ...

    @abstractmethod
    def delete_template(self, id: str) -> bool: ...

    @abstractmethod
    def runs(self) -> list[PipelineRun]: ...

    @abstractmethod
    def run(self, id: str) -> PipelineRun | None: ...

    @abstractmethod
    def save_run(self, run: PipelineRun, created: bool = False) -> None:
        """`created`: the first save, which also links the run to its template."""


class Notifier(ABC):
    @abstractmethod
    def notify(self, actor: Actor, payload: JsonObject) -> str | None:
        """POSTs `payload` to the actor's callback_url; the error, or None if it was received (or there is no URL)."""


@dataclass(frozen=True)
class Modules:
    ingesta: IngestaPort
    chunking: ChunkingPort
    data: DataPort


@dataclass(frozen=True)
class ActionContext:
    """What a task gets: the run, its stage, the stage's configuration (its params, the run's and the cycle
    iteration's) and the artifacts it can read."""

    run: PipelineRun
    stage: Stage
    config: JsonObject
    artifacts: JsonObject
    modules: Modules
    store: RunStore
    iteration: int | None = None


@dataclass(frozen=True)
class ActionOutput:
    artifacts: JsonObject = field(default_factory=dict)  # artifact → value (the names of `gives`)
    result: JsonValue = None  # a summary for the stage record
    experiment: str | None = None  # the chunking experiment the stage made


class Action(ABC):
    """One entry of the catalog: a kind of stage. `module` is the queue of its tasks (None for waits)."""

    name: str
    kind: StageKind
    module: str | None = None
    needs: tuple[str, ...] = ()
    gives: tuple[str, ...] = ()
    description: str = ""
    parameters: str = ""  # what it reads from its configuration, for GET /pipeline/actions

    def needs_of(self, stage: Stage) -> tuple[str, ...]:
        return self.needs

    def gives_of(self, stage: Stage) -> tuple[str, ...]:
        return self.gives

    def run(self, context: ActionContext) -> ActionOutput:
        raise ConflictError(f"{self.name} is done by an actor, not by the pipeline")


def as_object(value: JsonValue, where: str) -> JsonObject:
    """`value` as a JSON object (None is an empty one); anything else is InvalidRequest."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise InvalidRequest(f"{where} must be an object, not {value!r}")
    return value
