"""RunRegistry: the runs and experiments of this server session (in memory, with a lock); the past ones are read from
data (history.py)."""

import threading
from collections.abc import Callable
from dataclasses import replace

from common.clock import now
from embeddings.models import DocumentFailure, EmbeddingRun, RunKind, RunProgress, RunStatus


class RunRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, EmbeddingRun] = {}  # in start order
        self.on_done: Callable[[], None] = lambda: None  # what is stored changed

    def add(self, run: EmbeddingRun) -> None:
        with self._lock:
            self._runs[run.id] = run

    def get(self, id: str, kind: RunKind | None = None) -> EmbeddingRun | None:
        with self._lock:
            found = self._runs.get(id)
        return found if found is not None and (kind is None or found.kind is kind) else None

    def all(self, kind: RunKind | None = None) -> list[EmbeddingRun]:
        """Newest first."""
        with self._lock:
            return [r for r in reversed(self._runs.values()) if kind is None or r.kind is kind]

    def _change(self, id: str, change: Callable[[EmbeddingRun], EmbeddingRun]) -> None:
        with self._lock:
            if id in self._runs:
                self._runs[id] = change(self._runs[id])

    def begin(self, id: str) -> None:
        self._change(id, lambda r: replace(r, status=RunStatus.RUNNING, started=now()))

    def progress(self, id: str, progress: RunProgress) -> None:
        self._change(id, lambda r: replace(r, progress=progress))

    def failure(self, id: str, failure: DocumentFailure) -> None:
        self._change(id, lambda r: replace(r, failures=[*r.failures, failure]))

    def listed(self, id: str, sha256s: list[str]) -> None:
        """The documents a run without sha256s took when its turn came."""
        self._change(id, lambda r: replace(r, sha256s=list(sha256s)))

    def embedded(self, id: str, sha256: str) -> None:
        self._change(id, lambda r: replace(r, embedded=[*r.embedded, sha256]))

    def request_cancel(self, id: str, kind: RunKind) -> EmbeddingRun | None:
        """A queued or running one is asked to stop after its current document (feature 056); None if it ended."""
        with self._lock:
            run = self._runs.get(id)
            if run is None or run.kind is not kind or run.status not in (RunStatus.QUEUED, RunStatus.RUNNING):
                return None
            self._runs[id] = replace(run, cancel_requested=True)
            return self._runs[id]

    def stopping(self, id: str) -> bool:
        """Whether it was asked to stop."""
        with self._lock:
            run = self._runs.get(id)
            return run is not None and run.cancel_requested

    def finish(self, id: str, progress: RunProgress | None, error: str | None, stopped: bool = False) -> None:
        """`progress` None: the one it had (it stopped in the middle). `stopped`: it was asked to (feature 056)."""
        status = RunStatus.FAILED if error else RunStatus.CANCELLED if stopped else RunStatus.FINISHED
        self._change(
            id, lambda r: replace(r, status=status, finished=now(), progress=progress or r.progress, error=error)
        )

    def remove(self, id: str) -> None:
        """Deleted: it isn't shown any more."""
        with self._lock:
            self._runs.pop(id, None)

    def cancel(self, id: str) -> None:
        self._change(id, lambda r: replace(r, status=RunStatus.CANCELLED, finished=now()))
