"""WorkQueue: the pulls of llm, in order. One download at a time (they share the disk and the network), the others
wait here, up to a limit."""

import logging
import threading
from collections import deque
from collections.abc import Callable

from llm.config import MAX_WAITING

LOG = logging.getLogger(__name__)
LINE_FULL = "the line of pulls is full: try again when one has finished"


class WorkQueue:
    def __init__(self, limit: int = MAX_WAITING) -> None:
        self._limit = limit
        self._lock = threading.Lock()
        self._waiting: deque[tuple[str, Callable[[], None]]] = deque()
        self._active: str | None = None

    @property
    def active(self) -> str | None:
        with self._lock:
            return self._active

    @property
    def full(self) -> bool:
        """Whether a new job should be refused (against a flood, not an exact count)."""
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
            self._active = id  # taken now: two submits in a row start one worker
        threading.Thread(target=self._work, name="llm-queue", daemon=True).start()

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
            except Exception:  # a job deals with its errors: this only keeps the line moving, and says what got here
                LOG.exception("job %s broke", item[0])
