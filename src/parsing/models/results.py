"""What a check or a run of the parsing reports."""

from dataclasses import dataclass, field
from enum import StrEnum


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"
    INTERRUPTED = "interrupted"  # the server stopped while it was queued or running
    CANCELLED = "cancelled"  # taken out of the line before its turn, or stopped after a document (feature 056)


class DocumentState(StrEnum):
    WAITING = "waiting"  # not reached yet
    PARSED = "parsed"
    PARTIAL = "partial"  # stored, with pages left: another run resumes it
    ERROR = "error"
    SKIPPED = "skipped"  # already parsed with the same fingerprint
    MISSING = "missing"  # no RAW in data
    SIMULATED = "simulated"  # simulate: it would be parsed


@dataclass(frozen=True)
class DocumentResult:
    sha256: str
    state: DocumentState = DocumentState.WAITING
    resumed: bool = False  # it went on from a partial one
    ocr_pages: list[int] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True)
class RunProgress:
    total: int = 0  # documents of the run (repeated sha256 once)
    done: int = 0  # those already decided (parsed, partial, error, skipped, missing)
    parsed: int = 0
    partial: int = 0
    errors: int = 0
    skipped: int = 0
    missing: int = 0
    resumed: int = 0


@dataclass(frozen=True)
class ParsingRun:
    """A run of POST /runs: GET /runs/{id}. `parsed` are the sha256 that have a JSON now (parsed or partial): what
    whoever asked for the run passes on."""

    id: str
    status: RunStatus
    requested: str  # ISO
    fingerprint: str
    simulate: bool = False
    redo: bool = False
    started: str | None = None
    finished: str | None = None
    progress: RunProgress = field(default_factory=RunProgress)
    documents: list[DocumentResult] = field(default_factory=list)
    parsed: list[str] = field(default_factory=list)
    error: str | None = None  # why the whole run stopped (data down, Docling can't load...)
    cancel_requested: bool = False  # POST /runs/{id}/cancel: it stops after its current document (feature 056)


@dataclass(frozen=True)
class RunOutcome:
    progress: RunProgress
    error: str | None = None
    stopped: bool = False  # it was asked to stop: the documents after the one it was on weren't reached
