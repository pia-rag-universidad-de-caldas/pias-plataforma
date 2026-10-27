"""ExperimentRegistry: which experiment this server is running (one at a time, and never together with a production
run: both use Docling), and the thread each one runs in (it makes HTTP requests to the same server)."""

import threading

from chunking.adapters import HttpSession
from chunking.domain import ExperimentGraph, ExperimentRunner, now
from chunking.models import (
    Converter,
    ExperimentOutcome,
    ExperimentProgress,
    ExperimentRequest,
    ExperimentResults,
    FileResolution,
    SectionChunker,
)


class ExperimentRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: str | None = None

    @property
    def active(self) -> str | None:
        with self._lock:
            return self._active

    def start(self, id: str) -> bool:
        with self._lock:
            if self._active is not None:
                return False
            self._active = id
            return True

    def done(self, id: str) -> None:
        with self._lock:
            if self._active == id:
                self._active = None


def launch(
    registry: ExperimentRegistry,
    id: str,
    base_url: str,
    ingesta_path: str,
    data_path: str,
    converter: Converter,
    chunker: SectionChunker,
    request: ExperimentRequest,
    resolution: FileResolution,
) -> None:
    """Runs the experiment (already registered and stored) in its own thread; one HTTP session for all of it."""

    def execute() -> None:
        try:
            with HttpSession(base_url, ingesta_path, data_path) as session:
                store = session.experiments
                try:
                    outcome = ExperimentRunner.run(
                        session.source, store, converter, chunker, id, request, resolution, lambda _: None
                    )
                except Exception as error:  # a bug must not leave the experiment "running"
                    empty = ExperimentResults(0, 0, 0, 0, 0.0, 0.0, {}, {}, list(resolution.failures))
                    current = store.experiment(id)
                    progress = current.progress if current else None
                    outcome = ExperimentOutcome(
                        empty, progress or ExperimentProgress(), f"{type(error).__name__}: {error}"
                    )
                store.save(ExperimentGraph.finish(id, outcome.results, outcome.progress, outcome.error, now()))
        except Exception:  # data down at the very end: the experiment shows as interrupted
            pass
        finally:
            registry.done(id)

    threading.Thread(target=execute, name=f"chunking-experiment-{id}", daemon=True).start()
