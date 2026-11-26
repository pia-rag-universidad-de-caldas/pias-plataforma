"""The ingestions started from the API (feature 030): the in-memory registry, one at a time."""

import threading
import uuid
from collections.abc import Callable
from dataclasses import replace

from common.clock import now
from ingesta.models import (
    FileFailure,
    SourceCheck,
)

from .schemas import FileFailureItem, IngestionProgress, IngestionRun, IngestionState, IngestionSummary

MAX_FAILURES = 200  # file failures kept in a run (all of them count in its summary)


class IngestionRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, IngestionRun] = {}  # in start order
        self.on_done: Callable[[], None] = lambda: None  # what is stored changed

    def start(self, check: SourceCheck, total: int) -> IngestionRun | None:
        """Registers a new run unless another one is still running (None then)."""
        with self._lock:
            if any(r.estado is IngestionState.RUNNING for r in self._runs.values()):
                return None
            run = IngestionRun(
                uuid.uuid4().hex[:12], IngestionState.RUNNING, now(), None, check, IngestionProgress(0, total)
            )
            self._runs[run.id] = run
            return run

    def get(self, id: str) -> IngestionRun | None:
        with self._lock:
            return self._runs.get(id)

    def all(self) -> list[IngestionRun]:
        """Newest first."""
        with self._lock:
            return list(reversed(self._runs.values()))

    def progress(self, id: str, done: int) -> None:
        with self._lock:
            run = self._runs[id]
            self._runs[id] = replace(run, progreso=replace(run.progreso, copiados=done))

    def failure(self, id: str, failure: FileFailure) -> None:
        with self._lock:
            run = self._runs[id]
            if len(run.errores) < MAX_FAILURES:
                item = FileFailureItem(failure.origin, failure.error, failure.target)
                self._runs[id] = replace(run, errores=[*run.errores, item])

    def finish(self, id: str, result: IngestionSummary | None, error: str | None) -> None:
        with self._lock:
            run = self._runs[id]
            state = IngestionState.FAILED if error else IngestionState.FINISHED
            progress = replace(run.progreso, copiados=result.copiados) if result else run.progreso
            self._runs[id] = replace(run, estado=state, fin=now(), progreso=progress, resultado=result, error=error)
