"""What a production run (feature 023) and an experiment (feature 025) report while they go and when they end."""

from dataclasses import dataclass, field
from enum import StrEnum

from .concepts import ChunkingParameters, ExperimentFile


class RunStatus(StrEnum):
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"  # the run itself stopped (a document that fails doesn't stop it)


@dataclass(frozen=True)
class DocumentFailure:
    error: str
    origin: str | None = None  # None if the document was asked for by a sha256 ingesta doesn't have
    sha256: str | None = None


@dataclass(frozen=True)
class RunProgress:
    """Counters of a run, reported by the Runner after each document."""

    pending: int = 0  # documents selected to be processed (with simulate: the ones that would be)
    chunked: int = 0
    chunks: int = 0  # chunks written
    skipped: int = 0  # already chunked with the same sha256 and parameters (or in error, without retry_errors)
    errors: int = 0


@dataclass(frozen=True)
class RunOutcome:
    """How the Runner ended: its counters and, if the run itself stopped, why."""

    progress: RunProgress
    error: str | None = None


@dataclass(frozen=True)
class ChunkingRun:
    id: str
    status: RunStatus
    started: str  # ISO
    simulate: bool
    parameters: ChunkingParameters  # what it chunks with
    fingerprint: str  # of those parameters
    finished: str | None = None  # ISO; None while running
    progress: RunProgress = field(default_factory=RunProgress)
    failures: list[DocumentFailure] = field(default_factory=list)
    error: str | None = None  # why the run itself stopped (status failed)


@dataclass(frozen=True)
class FileResolution:
    """The files an experiment would take, and the ones it couldn't (an unknown sha256...)."""

    files: list[ExperimentFile]
    failures: list[DocumentFailure]


class ExperimentStatus(StrEnum):
    """The VALUES are stored (EXPERIMENTO.estado), except INTERRUPTED: a `running` one this server isn't running
    (the server stopped in the middle)."""

    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True)
class ExperimentProgress:
    files: int = 0  # files that enter
    done: int = 0  # documents finished (chunked or in error)
    converted: int = 0  # converted with Docling in this experiment
    reused: int = 0  # conversions that already existed
    errors: int = 0
    sections: int = 0
    chunks: int = 0


@dataclass(frozen=True)
class TokenStats:
    min: int
    mean: float
    p90: int
    max: int


@dataclass(frozen=True)
class GroupResult:
    """What a strategy (or a rule) produced across the experiment."""

    sections: int
    chunks: int
    tokens: TokenStats | None  # None without chunks
    chunking_seconds: float


@dataclass(frozen=True)
class ExperimentResults:
    """The record of results stored on the EXPERIMENTO (`resultados`)."""

    documents: int
    converted: int
    reused: int
    errors: int
    conversion_seconds: float  # Docling time spent in this experiment
    chunking_seconds: float
    by_strategy: dict[str, GroupResult]
    by_rule: dict[str, GroupResult]  # "0", "1"... (index of the rule) and "default"
    failures: list[DocumentFailure]


@dataclass(frozen=True)
class ExperimentOutcome:
    """How an experiment ended: its record of results and, if it stopped (ingesta or data down), why."""

    results: ExperimentResults
    progress: ExperimentProgress
    error: str | None = None


class PromotionKind(StrEnum):
    """What promoting an experiment copies to the official graph (feature 028)."""

    CONVERSION = "conversion"  # a conversion-only experiment: its JSON
    CHUNKS = "chunks"  # an experiment with a plan: its sections and chunks, under the official JSON


@dataclass(frozen=True)
class PromotionOutcome:
    experiment: str
    kind: PromotionKind
    promoted: int  # documents copied
    failed: list[DocumentFailure]
