"""ExperimentRegistry: the experiments this server has in line or running (feature 039), with their progress in memory
for those who watch them."""

import threading
from collections.abc import Callable
from dataclasses import dataclass, field, replace

from chunking.api.work_queue import WorkQueue
from chunking.models import ExperimentProgress, ExperimentRecord, ExperimentStatus


@dataclass(frozen=True)
class LiveExperiment:
    id: str
    name: str
    strategies: tuple[str, ...]  # how it chunks, for /processes
    requested: str
    started: str | None = None
    progress: ExperimentProgress = field(default_factory=ExperimentProgress)


class ExperimentRegistry:
    def __init__(self, queue: WorkQueue) -> None:
        self._queue = queue
        self._lock = threading.Lock()
        self._live: dict[str, LiveExperiment] = {}
        self.on_done: Callable[[], None] = lambda: None  # what is stored changed

    @property
    def active(self) -> str | None:
        """The one running, if it is an experiment."""
        running = self._queue.active
        with self._lock:
            return running if running in self._live else None

    def status(self, record: ExperimentRecord) -> ExperimentStatus:
        """A stored queued or running one this server doesn't have: it stopped in the middle."""
        with self._lock:
            live = record.id in self._live
        alive = record.status in (ExperimentStatus.QUEUED, ExperimentStatus.RUNNING)
        return ExperimentStatus.INTERRUPTED if alive and not live else record.status

    def has(self, id: str) -> bool:
        """In line or running in this server."""
        with self._lock:
            return id in self._live

    def live(self) -> list[LiveExperiment]:
        with self._lock:
            return list(self._live.values())

    def add(self, experiment: LiveExperiment) -> None:
        with self._lock:
            self._live[experiment.id] = experiment

    def begin(self, id: str, at: str) -> None:
        with self._lock:
            self._live[id] = replace(self._live[id], started=at)

    def progress(self, id: str, progress: ExperimentProgress) -> None:
        with self._lock:
            self._live[id] = replace(self._live[id], progress=progress)

    def done(self, id: str) -> None:
        with self._lock:
            self._live.pop(id, None)
        self.on_done()

    def cancel(self, id: str) -> None:
        """Takes it out of the line, if it is there."""
        if self._queue.cancel(id):
            self.done(id)
