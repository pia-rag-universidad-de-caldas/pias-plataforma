"""RunRegistry: the chunking runs of this server session (in memory, with a lock), and the thread each one runs in.

A run makes HTTP requests to the same server (ingesta, data), so it never runs in the event loop: it gets its own
threading.Thread, and the server keeps answering (those requests included). Only one run at a time.
"""

import threading
from dataclasses import replace
from datetime import datetime

from chunking.adapters import HttpSession
from chunking.config import CHUNK_PAGE_SIZE
from chunking.domain import Runner
from chunking.models import (
    ChunkingParameters,
    ChunkingRun,
    Converter,
    DocumentFailure,
    RunOutcome,
    RunProgress,
    RunRequest,
    RunStatus,
)


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class RunRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, ChunkingRun] = {}  # in start order

    def start(self, run: ChunkingRun) -> bool:
        """Registers `run` unless another one is still running (False then)."""
        with self._lock:
            if any(r.status == RunStatus.RUNNING for r in self._runs.values()):
                return False
            self._runs[run.id] = run
            return True

    def get(self, id: str) -> ChunkingRun | None:
        with self._lock:
            return self._runs.get(id)

    def all(self) -> list[ChunkingRun]:
        """Newest first."""
        with self._lock:
            return list(reversed(self._runs.values()))

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
                status=RunStatus.FAILED if outcome.error else RunStatus.FINISHED,
                finished=now(),
                progress=outcome.progress,
                error=outcome.error,
            )


def launch(
    registry: RunRegistry,
    run: ChunkingRun,
    base_url: str,
    ingesta_path: str,
    data_path: str,
    converter: Converter,
    request: RunRequest,
    parameters: ChunkingParameters,
) -> None:
    """Runs `run` (already registered) in its own thread; one HTTP session for the whole run."""

    def execute() -> None:
        try:
            with HttpSession(base_url, ingesta_path, data_path) as session:
                outcome = Runner.run(
                    session.source,
                    session.sink,
                    converter,
                    request,
                    parameters,
                    CHUNK_PAGE_SIZE,
                    lambda progress: registry.progress(run.id, progress),
                    lambda failure: registry.failure(run.id, failure),
                )
        except Exception as error:  # a bug must not leave the run "running" forever (and block the next ones)
            current = registry.get(run.id)
            outcome = RunOutcome(current.progress if current else RunProgress(), f"{type(error).__name__}: {error}")
        registry.finish(run.id, outcome)

    threading.Thread(target=execute, name=f"chunking-run-{run.id}", daemon=True).start()
