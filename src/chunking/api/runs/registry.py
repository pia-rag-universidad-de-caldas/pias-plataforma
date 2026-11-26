"""RunRegistry: the runs of this server session (in memory, with a lock); those of before are read from the graph."""

import threading
from collections.abc import Callable
from dataclasses import replace

from chunking.models import ChunkingRun, DocumentFailure, RunOutcome, RunProgress, RunStatus
from common.clock import now


class RunRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, ChunkingRun] = {}  # in request order
        self.on_done: Callable[[], None] = lambda: None  # what is stored changed

    def add(self, run: ChunkingRun) -> None:
        """A new one, or one that is resumed (it goes back to the end of the order)."""
        with self._lock:
            self._runs.pop(run.id, None)
            self._runs[run.id] = run

    def begin(self, id: str, sha256s: list[str]) -> None:
        """Its turn came, over these documents (now frozen)."""
        with self._lock:
            self._runs[id] = replace(
                self._runs[id], status=RunStatus.RUNNING, started=now(), sha256s=sha256s, frozen=True
            )

    def get(self, id: str) -> ChunkingRun | None:
        with self._lock:
            return self._runs.get(id)

    def all(self) -> list[ChunkingRun]:
        """Newest first."""
        with self._lock:
            return list(reversed(self._runs.values()))

    def alive(self, id: str) -> bool:
        with self._lock:
            run = self._runs.get(id)
            return run is not None and run.status in (RunStatus.QUEUED, RunStatus.RUNNING)

    def request_cancel(self, id: str) -> ChunkingRun | None:
        """A queued or running run is asked to stop after its current document (feature 056); None if it ended."""
        with self._lock:
            run = self._runs.get(id)
            if run is None or run.status not in (RunStatus.QUEUED, RunStatus.RUNNING):
                return None
            self._runs[id] = replace(run, cancel_requested=True)
            return self._runs[id]

    def stopping(self, id: str) -> bool:
        """Whether the run was asked to stop."""
        with self._lock:
            run = self._runs.get(id)
            return run is not None and run.cancel_requested

    def progress(self, id: str, progress: RunProgress) -> None:
        with self._lock:
            self._runs[id] = replace(self._runs[id], progress=progress)

    def failure(self, id: str, failure: DocumentFailure) -> None:
        with self._lock:
            run = self._runs[id]
            self._runs[id] = replace(run, failures=[*run.failures, failure])

    def finish(self, id: str, outcome: RunOutcome) -> None:
        with self._lock:
            self._runs[id] = replace(
                self._runs[id],
                status=outcome.status,
                finished=now(),
                progress=outcome.progress,
                failures=outcome.failures,
                chunked=outcome.chunked,
                error=outcome.error,
            )

    def cancel(self, id: str) -> None:
        """Taken out of the line before it ran: it ends as interrupted (and can be resumed)."""
        with self._lock:
            run = self._runs.get(id)
            if run is not None:
                self._runs[id] = replace(run, status=RunStatus.INTERRUPTED, finished=now())
