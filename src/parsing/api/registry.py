"""RunRegistry: the parsing runs of this server session (in memory, with a lock)."""

import threading
from collections.abc import Callable
from dataclasses import replace

from common.clock import now
from parsing.models import DocumentResult, DocumentState, ParsingRun, RunOutcome, RunProgress, RunStatus

_HAS_JSON = frozenset({DocumentState.PARSED, DocumentState.PARTIAL, DocumentState.SKIPPED})  # skipped: already has it


class RunRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, ParsingRun] = {}  # in start order
        self.on_done: Callable[[], None] = lambda: None  # what is stored changed

    def add(self, run: ParsingRun) -> None:
        with self._lock:
            self._runs[run.id] = run

    def get(self, id: str) -> ParsingRun | None:
        with self._lock:
            return self._runs.get(id)

    def all(self) -> list[ParsingRun]:
        """Newest first."""
        with self._lock:
            return list(reversed(self._runs.values()))

    def begin(self, id: str) -> None:
        with self._lock:
            self._runs[id] = replace(self._runs[id], status=RunStatus.RUNNING, started=now())

    def document(self, id: str, result: DocumentResult, progress: RunProgress) -> None:
        """A document was decided: its result replaces its waiting entry."""
        with self._lock:
            run = self._runs[id]
            documents = [result if d.sha256 == result.sha256 else d for d in run.documents]
            parsed = [*run.parsed, result.sha256] if result.state in _HAS_JSON else run.parsed
            self._runs[id] = replace(run, documents=documents, progress=progress, parsed=parsed)

    def request_cancel(self, id: str) -> ParsingRun | None:
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

    def finish(self, id: str, outcome: RunOutcome) -> None:
        with self._lock:
            if outcome.error:
                ended = RunStatus.FAILED
            elif outcome.stopped:
                ended = RunStatus.CANCELLED
            else:
                ended = RunStatus.FINISHED
            self._runs[id] = replace(
                self._runs[id],
                status=ended,
                finished=now(),
                progress=outcome.progress,
                error=outcome.error,
            )

    def cancel(self, id: str) -> None:
        with self._lock:
            self._runs[id] = replace(self._runs[id], status=RunStatus.CANCELLED, finished=now())
