"""What the pipeline's domain needs from the outside (implemented in adapters/, over HTTP) and its errors."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from pipeline.config import SPECIAL_TOKENS

from .concepts import Actor, JsonObject, JsonValue, Stage, StageKind, Template
from .requests import Selection
from .results import PipelineRun, RunStatus
from .watch import JobWatch


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
class JobOutcome:
    """How a job of another module ended (an ingestion, a parsing run, a chunking run, an embeddings run or an
    experiment): its id, its status, why it failed and the sha256s it says it did."""

    id: str
    status: str
    error: str | None = None
    sha256s: tuple[str, ...] = ()
    succeeded: bool = False


@dataclass(frozen=True)
class EmbeddingModel:
    """A model embeddings admits: its default and its largest token limit (both counting its special tokens and its
    passage prefix). Feature 062: how many tokens of its own a chunk may have (`passage_budget`: the limit minus the
    special tokens and the prefix; `default_passage_budget`: the same over the default; `official_passage_budget`:
    an official chunk, which also carries the course heading). None when embeddings can't count them (without its
    extra): then the limit minus the SPECIAL_TOKENS, as before."""

    name: str
    default_tokens: int
    max_tokens: int
    default: bool = False
    passage_budget: int | None = None
    default_passage_budget: int | None = None
    official_passage_budget: int | None = None

    @property
    def budget(self) -> int:
        """The most tokens (its own) a chunk may have under its largest limit."""
        return self.passage_budget if self.passage_budget is not None else self.max_tokens - SPECIAL_TOKENS

    @property
    def default_budget(self) -> int:
        """The same under its default limit."""
        found = self.default_passage_budget
        return found if found is not None else self.default_tokens - SPECIAL_TOKENS

    @property
    def official_budget(self) -> int:
        """An official chunk's: it also takes the course heading (feature 057)."""
        return self.official_passage_budget if self.official_passage_budget is not None else self.budget

    @property
    def overhead(self) -> int:
        """What the limit counts besides the chunk: its special tokens and its passage prefix. The embeddings limit
        of chunks of `n` tokens is n + overhead."""
        return self.max_tokens - self.budget


@dataclass(frozen=True)
class SelectedPage:
    """One page of POST /data/documents/select (feature 062): the sha256s of the documents the selection takes."""

    total: int
    sha256s: tuple[str, ...]
    pages: int


@dataclass(frozen=True)
class ExperimentState:
    """A chunking experiment as data has it (its EXPERIMENTO node): `estado` and `error`."""

    id: str
    status: str
    error: str | None = None


@dataclass(frozen=True)
class ChunkingExperimentInfo:
    """A chunking experiment as chunking shows it: its status and the parameters it chunks with (`chunking`:
    {chunker, tokenizer, max_tokens, merge_peers} or, feature 062, {chunker, fit: [{tokenizer, max_tokens}], ...})."""

    id: str
    status: str
    chunking: JsonObject


@dataclass(frozen=True)
class AddedDocuments:
    """The answer of POST /chunking/experiments/{id}/documents (feature 062)."""

    added: int
    already: int
    unparsed: int
    total: int


@dataclass(frozen=True)
class EmbeddingsExperimentInfo:
    """An embeddings experiment over a chunking experiment: its model, status and what it still lacks (`pending`:
    None if embeddings doesn't say)."""

    id: str
    model: str
    status: str
    pending: int | None = None


@dataclass(frozen=True)
class LlmModel:
    """A model llm admits (feature 047): its context window, if it says one, and whether it is downloaded."""

    name: str
    context: int | None = None
    vision: bool = False
    installed: bool = False
    default: bool = False


class IngestaPort(ABC):
    @abstractmethod
    def page(self, selection: Selection, page: int, per_page: int) -> SourcePage: ...

    @abstractmethod
    def has(self, sha256: str) -> bool:
        """Whether a chunkable file has that content."""

    @abstractmethod
    def ingest(self, watch: JobWatch | None = None) -> JobOutcome:
        """Runs an ingestion (organizes and puts the current files in data as RAW) and waits until it ends."""


class ParsingPort(ABC):
    @abstractmethod
    def parse(self, sha256s: list[str], watch: JobWatch | None = None) -> JobOutcome:
        """Parses them (waiting its turn while parsing is busy) and waits until it ends; with none, every current RAW
        still to parse (parsing decides which, from data). `watch` (feature 056) can stop it after its current
        document."""


class ChunkingPort(ABC):
    @abstractmethod
    def experiment(self, body: JsonObject, watch: JobWatch | None = None) -> JobOutcome:
        """Starts the experiment (waiting its turn while chunking is busy) and waits until it ends."""

    @abstractmethod
    def apply(self, experiment: str) -> None:
        """Its configuration becomes the active one."""

    @abstractmethod
    def promote(self, sha256s: list[str], watch: JobWatch | None = None) -> JobOutcome:
        """Chunks them with the active configuration into the official graph, and waits until it ends."""

    @abstractmethod
    def start_experiment(self, body: JsonObject, watch: JobWatch | None = None) -> str:
        """Puts a new experiment in chunking's line (waiting while the line is full) and gives its id at once:
        whether it ended is read in data (feature 062)."""

    @abstractmethod
    def experiment_info(self, experiment: str) -> ChunkingExperimentInfo | None:
        """The experiment's status and parameters; None if chunking doesn't have it."""

    @abstractmethod
    def add_documents(self, experiment: str, sha256s: list[str], watch: JobWatch | None = None) -> AddedDocuments:
        """Adds them to the experiment, which chunks what is new (feature 062); it doesn't wait."""

    @abstractmethod
    def resume_experiment(self, experiment: str, watch: JobWatch | None = None) -> None:
        """Puts a partial, failed or interrupted experiment back in line; it doesn't wait."""

    @abstractmethod
    def config(self) -> JsonObject | None:
        """The active configuration's parameters (GET /chunking/config `chunking`); None if there is none."""


class EmbeddingsPort(ABC):
    @abstractmethod
    def models(self) -> list[EmbeddingModel]: ...

    @abstractmethod
    def embed(self, sha256s: list[str], watch: JobWatch | None = None) -> JobOutcome:
        """Embeds the official chunks of those documents with the active configuration, and waits until it ends."""

    @abstractmethod
    def experiment(self, body: JsonObject, watch: JobWatch | None = None) -> JobOutcome:
        """Embeds a chunking experiment's chunks with a model, apart from the official, and waits until it ends."""

    @abstractmethod
    def apply(self, experiment: str) -> None: ...

    @abstractmethod
    def experiments_of(self, chunking_experiment: str) -> list[EmbeddingsExperimentInfo]:
        """The embeddings experiments over that chunking experiment, newest first (feature 059)."""

    @abstractmethod
    def resume(self, experiment: str, watch: JobWatch | None = None) -> JobOutcome:
        """Embeds what that experiment still lacks (feature 062) and waits until it ends; an experiment running
        already is only waited for, one that lacks nothing isn't started."""

    @abstractmethod
    def embed_model(self, sha256s: list[str], model: str, watch: JobWatch | None = None) -> JobOutcome:
        """Embeds the official chunks of those documents with `model`, next to the active one, and waits."""


class LlmPort(ABC):
    @abstractmethod
    def models(self) -> list[LlmModel]:
        """The admitted models, each saying whether it is downloaded."""

    @abstractmethod
    def apply(self, config: JsonObject) -> None:
        """`config` ({model, temperature?, num_ctx?, max_tokens?, system?}) becomes llm's active configuration."""


class DataPort(ABC):
    @abstractmethod
    def json_page(self, page: int, per_page: int) -> IdPage:
        """One page of the JSON nodes (the parsed documents)."""

    @abstractmethod
    def select(
        self, universe: str, files: JsonObject, exclude_experiment: str | None, page: int, per_page: int
    ) -> SelectedPage:
        """One page of the documents a selection takes (POST /data/documents/select, feature 062): of the parsed
        (`parsed`) or the officially chunked (`chunked`), without those a chunking experiment has."""

    @abstractmethod
    def wait_experiment(self, experiment: str, watch: JobWatch | None = None) -> ExperimentState:
        """Reads the chunking experiment in data until it isn't queued nor running any more (feature 062: data says
        when chunking ended, not chunking)."""


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

    def runs_by_status(self, status: RunStatus, actor: str | None = None) -> list[PipelineRun]:
        """Runs in one state, optionally for a waiting actor; stores may use an indexed query."""
        return [
            run
            for run in self.runs()
            if run.status == status and (actor is None or (run.waiting and run.waiting.actor == actor))
        ]

    def waiting_runs(self, actor: str | None = None) -> list[PipelineRun]:
        """Waiting runs for an actor. Stores can override this with an indexed graph query."""
        return self.runs_by_status(RunStatus.WAITING, actor)

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
    parsing: ParsingPort
    chunking: ChunkingPort
    embeddings: EmbeddingsPort
    data: DataPort
    llm: LlmPort


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
    part: int | None = None  # the part of the batch it works on (feature 056)
    watch: JobWatch = field(default_factory=JobWatch)  # cancelling the run stops the job it waits for


@dataclass(frozen=True)
class ActionOutput:
    artifacts: JsonObject = field(default_factory=dict)  # artifact → value (the names of `gives`)
    result: JsonValue = None  # a summary for the stage record
    experiment: str | None = None  # the chunking experiment the stage made
    embeddings_experiment: str | None = None  # the embeddings experiment the stage made


class Action(ABC):
    """One entry of the catalog: a kind of stage. `module` is the queue of its tasks (None for waits)."""

    name: str
    kind: StageKind
    module: str | None = None
    needs: tuple[str, ...] = ()
    gives: tuple[str, ...] = ()
    description: str = ""
    parameters: str = ""  # what it reads from its configuration, for GET /pipeline/actions
    rewinds: bool = False  # resumed at it, the run goes back to the stage that gave what it needs (feature 062)

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
