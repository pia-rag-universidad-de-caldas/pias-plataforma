"""PullRegistry: the pulls of this server session, in memory only (with a lock): a pull leaves nothing in data, Ollama
keeps the model."""

import threading
from collections.abc import Callable
from dataclasses import replace

from common.clock import now
from llm.models import ModelPull, PullProgress, PullStatus


class PullRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pulls: dict[str, ModelPull] = {}  # in start order

    def add(self, pull: ModelPull) -> None:
        with self._lock:
            self._pulls[pull.id] = pull

    def get(self, id: str) -> ModelPull | None:
        with self._lock:
            return self._pulls.get(id)

    def all(self) -> list[ModelPull]:
        """Newest first."""
        with self._lock:
            return list(reversed(self._pulls.values()))

    def _change(self, id: str, change: Callable[[ModelPull], ModelPull]) -> None:
        with self._lock:
            if id in self._pulls:
                self._pulls[id] = change(self._pulls[id])

    def begin(self, id: str) -> None:
        self._change(id, lambda p: replace(p, status=PullStatus.RUNNING, started=now()))

    def progress(self, id: str, step: PullProgress) -> None:
        """A step without bytes (verifying, writing the manifest) keeps the bytes of the last layer."""
        if step.total:
            self._change(id, lambda p: replace(p, step=step.status, completed=step.completed, total=step.total))
        else:
            self._change(id, lambda p: replace(p, step=step.status))

    def finish(self, id: str, error: str | None) -> None:
        status = PullStatus.FAILED if error else PullStatus.FINISHED
        self._change(id, lambda p: replace(p, status=status, finished=now(), error=error))
