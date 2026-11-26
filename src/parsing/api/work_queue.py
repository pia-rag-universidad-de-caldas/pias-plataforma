"""WorkQueue: what parsing runs, in order. A run uses Docling: one at a time, the others wait here, up to a limit."""

import logging
import threading
from collections import deque
from collections.abc import Callable

from parsing.config import MAX_WAITING

LOG = logging.getLogger(__name__)
LINE_FULL = "the line of parsing is full: try again when something has finished"


class WorkQueue:
    def __init__(self, limit: int = MAX_WAITING) -> None:
        self._limit = limit
        self._lock = threading.Lock()
        self._waiting: deque[tuple[str, Callable[[], None]]] = deque()
        self._active: str | None = None

    @property
    def full(self) -> bool:
        with self._lock:
            return len(self._waiting) >= self._limit

    def waiting(self) -> tuple[str, ...]:
        """The ids in line, the next one first."""
        with self._lock:
            return tuple(id for id, _ in self._waiting)

    def submit(self, id: str, job: Callable[[], None]) -> None:
        """`job` runs in a thread of this queue when its turn comes; it must deal with its own errors."""
        with self._lock:
            self._waiting.append((id, job))
            if self._active is not None:
                return
            self._active = id
        threading.Thread(target=self._work, name="parsing-queue", daemon=True).start()

    def cancel(self, id: str) -> bool:
        """Takes `id` out of the line; False if it isn't waiting (it may be running)."""
        with self._lock:
            found = next((item for item in self._waiting if item[0] == id and id != self._active), None)
            if found is None:
                return False
            self._waiting.remove(found)
            return True

    def _next(self) -> tuple[str, Callable[[], None]] | None:
        with self._lock:
            if not self._waiting:
                self._active = None
                return None
            self._active = self._waiting[0][0]
            return self._waiting.popleft()

    def _work(self) -> None:
        while (item := self._next()) is not None:
            try:
                item[1]()
            except Exception:  # a job deals with its errors: this only keeps the line moving
                LOG.exception("job %s broke", item[0])
