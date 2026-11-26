"""WorkQueue: what chunking runs, in order (feature 039). Runs and experiments go one at a time: what arrives while
another one runs waits here, up to a limit (feature 040)."""

import logging
import threading
from collections import deque
from collections.abc import Callable

LOG = logging.getLogger(__name__)
MAX_WAITING = 100  # jobs in line; more would only keep memory and never finish in a useful time
LINE_FULL = "the line of chunking is full: try again when something has finished"


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
    def busy(self) -> bool:
        with self._lock:
            return self._active is not None

    @property
    def full(self) -> bool:
        """Whether a new job should be refused; the routes ask before storing anything. Two requests at the same time
        may both pass, so the limit can go over by a few: it is there against a flood, not as an exact count."""
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
        threading.Thread(target=self._work, name="chunking-queue", daemon=True).start()

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
            except Exception:  # a job deals with its errors: this only keeps the line moving, and says what got here
                LOG.exception("job %s broke", item[0])
