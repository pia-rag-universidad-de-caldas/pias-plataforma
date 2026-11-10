"""What a run or an experiment reports (GET /runs/{id}, GET /experiments/{id}) ."""

from dataclasses import dataclass, field
from enum import StrEnum

from .concepts import EmbeddingConfig


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    FINISHED = "finished"  # it went over every document (some may have failed: see `failures`)
    FAILED = "failed"  # data or the model went down, or a bug: `error` says why
    INTERRUPTED = "interrupted"  # stored queued or running, but this server isn't running it (it was restarted)
    CANCELLED = "cancelled"  # taken out of the line before its turn


ALIVE = frozenset({RunStatus.QUEUED, RunStatus.RUNNING})


class RunKind(StrEnum):
    RUN = "run"  # production: the official chunks (FRAGMENTOS) of some documents
    EXPERIMENT = "experiment"  # laboratory: the chunks (EXP_CHUNK) of a chunking experiment


@dataclass(frozen=True)
class RunProgress:
    total: int = 0  # documents to go over
    embedded: int = 0
    chunks: int = 0  # vectors calculated
    unchanged: int = 0  # already embedded from the same chunks and model
    skipped: int = 0  # not chunked yet, or chunked in error
    missing: int = 0  # a sha256 asked for with no JSON in data
    errors: int = 0  # a chunk over the limit, or data refused its vectors

    @property
    def done(self) -> int:
        return self.embedded + self.unchanged + self.skipped + self.missing + self.errors


@dataclass(frozen=True)
class DroppedVectors:
    """What DELETE /models/{name}/vectors removed (feature 055)."""

    model: str
    index: str  # its FRAGMENTOS index
    index_dropped: bool  # False if it had none
    documents: int  # official JSON whose fingerprint of that model was removed


@dataclass(frozen=True)
class DocumentFailure:
    sha256: str
    error: str


@dataclass(frozen=True)
class EmbeddingRun:
    """A production run or an experiment: the same shape, told apart by `kind`."""

    id: str
    kind: RunKind
    status: RunStatus
    requested: str  # ISO
    config: EmbeddingConfig  # what it uses: the active one when it was queued, or the experiment's
    sha256s: list[str] = field(default_factory=list)  # a run: the ones asked for (repeated ones once)
    chunking_experiment: str | None = None  # an experiment: the chunking experiment whose chunks it embeds
    name: str = ""
    description: str = ""
    simulate: bool = False
    force: bool = False
    started: str | None = None
    finished: str | None = None
    progress: RunProgress = field(default_factory=RunProgress)
    failures: list[DocumentFailure] = field(default_factory=list)
    embedded: list[str] = field(default_factory=list)  # sha256s whose chunks have vectors now: what the pipeline reads
    error: str | None = None  # why the whole run stopped
