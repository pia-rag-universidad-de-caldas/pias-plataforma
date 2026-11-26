"""What a run (the official chunking) and an experiment report while they go and when they end (features 043 and
045)."""

from dataclasses import dataclass, field
from enum import StrEnum

from .concepts import ChunkingParameters


class RunStatus(StrEnum):
    """Of a run. The VALUES are stored (CORRIDA_CHUNKING.estado)."""

    QUEUED = "queued"
    RUNNING = "running"
    FINISHED = "finished"  # every document that entered is chunked (or was already)
    PARTIAL = "partial"  # it ended, but some document that entered failed: it can be resumed
    FAILED = "failed"  # the run itself stopped (a document that fails doesn't stop it)
    INTERRUPTED = "interrupted"  # the server stopped while it was queued or running, or it was cancelled (056)

    @staticmethod
    def ended(error: str | None, failed: int) -> "RunStatus":
        """How a run (or an experiment) that got to its end ended."""
        return RunStatus.FAILED if error else RunStatus.PARTIAL if failed else RunStatus.FINISHED


RESUMABLE = frozenset({RunStatus.PARTIAL, RunStatus.FAILED, RunStatus.INTERRUPTED})  # what POST .../resume takes


@dataclass(frozen=True)
class DocumentFailure:
    sha256: str
    error: str


UNPARSED = "sin_parseo: parse it first (POST /parsing/runs)"  # the error of a sha256 without a parsed JSON


@dataclass(frozen=True)
class RunProgress:
    pending: int = 0  # documents to chunk (with simulate: those that would be chunked)
    chunked: int = 0
    chunks: int = 0  # chunks written
    skipped: int = 0  # already chunked with the same parameters over the same parse
    unparsed: int = 0  # sin_parseo
    errors: int = 0


@dataclass(frozen=True)
class RunOutcome:
    progress: RunProgress
    chunked: list[str]  # the sha256s chunked with its configuration, the skipped ones too (what goes to embeddings)
    failures: list[DocumentFailure] = field(default_factory=list)
    error: str | None = None  # why the run itself stopped
    stopped: bool = False  # it was asked to stop (feature 056): the documents after the one it was on weren't reached

    @property
    def status(self) -> RunStatus:
        if self.stopped and not self.error:
            return RunStatus.INTERRUPTED  # resumable: POST /runs/{id}/resume goes on with its list
        return RunStatus.ended(self.error, self.progress.errors)


@dataclass(frozen=True)
class ChunkingRun:
    """A POST /chunking/runs: what it chunks, with what, and how it is going. The list is frozen: the sha256s asked
    for, or what was missing (one page of it, or all) when its turn came; a resume goes over it again."""

    id: str
    status: RunStatus
    requested: str  # ISO
    simulate: bool
    parameters: ChunkingParameters  # the active configuration when it was asked for
    sha256s: list[str]  # the documents it goes over
    frozen: bool = True  # False: it takes what is missing when its turn comes (sha256s still empty)
    page: int | None = None  # of what is missing (with per_page); None: all of it
    per_page: int | None = None
    experiment: str | None = None  # the experiment the active configuration came from
    started: str | None = None
    finished: str | None = None
    progress: RunProgress = field(default_factory=RunProgress)
    failures: list[DocumentFailure] = field(default_factory=list)
    chunked: list[str] = field(default_factory=list)
    error: str | None = None
    resumed: int = 0  # how many times it was resumed
    cancel_requested: bool = False  # POST /runs/{id}/cancel: it stops after its current document (feature 056)

    @property
    def documents(self) -> int:
        return len(self.sha256s)


class ExperimentStatus(StrEnum):
    """The VALUES are stored (EXPERIMENTO.estado), except INTERRUPTED: a `queued` or `running` one this server doesn't
    have (the server stopped in the middle)."""

    QUEUED = "queued"
    RUNNING = "running"
    FINISHED = "finished"
    PARTIAL = "partial"  # it ended, but some document that entered failed: it can be resumed
    FAILED = "failed"
    INTERRUPTED = "interrupted"


RESUMABLE_EXPERIMENTS = frozenset({ExperimentStatus.PARTIAL, ExperimentStatus.FAILED, ExperimentStatus.INTERRUPTED})


@dataclass(frozen=True)
class ExperimentProgress:
    files: int = 0  # documents that enter (parsed ones)
    done: int = 0  # chunked or in error
    errors: int = 0
    chunks: int = 0


@dataclass(frozen=True)
class TokenStats:
    min: int
    mean: float
    p90: int
    max: int


@dataclass(frozen=True)
class DocumentResult:
    sha256: str
    chunks: int
    tokens: int


@dataclass(frozen=True)
class ExperimentResults:
    """The record of results stored on the EXPERIMENTO (`resultados`)."""

    documents: int
    chunked: int
    errors: int
    unparsed: int
    chunks: int
    tokens: TokenStats | None  # over every chunk; None without chunks
    seconds: float
    by_document: list[DocumentResult]  # the sha256s chunked, with their numbers
    failures: list[DocumentFailure]


@dataclass(frozen=True)
class ExperimentOutcome:
    results: ExperimentResults
    progress: ExperimentProgress
    error: str | None = None  # why it stopped (data down, the tokenizer can't be loaded)
