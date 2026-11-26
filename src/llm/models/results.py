"""What a pull reports (GET /models/pulls/{id}): kept in memory only, for this server session."""

from dataclasses import dataclass
from enum import StrEnum


class PullStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"  # Ollama went down or refused it: `error` says why


ALIVE = frozenset({PullStatus.QUEUED, PullStatus.RUNNING})


@dataclass(frozen=True)
class PullProgress:
    """One line of Ollama's progress: what it is doing and, while it downloads a layer, its bytes."""

    status: str  # "pulling manifest", "pulling <digest>", "verifying sha256 digest", "success"...
    completed: int = 0
    total: int = 0


@dataclass(frozen=True)
class ModelPull:
    id: str
    model: str
    status: PullStatus
    requested: str  # ISO
    started: str | None = None
    finished: str | None = None
    step: str | None = None  # Ollama's last status line
    completed: int = 0  # bytes of the layer being downloaded
    total: int = 0
    error: str | None = None
