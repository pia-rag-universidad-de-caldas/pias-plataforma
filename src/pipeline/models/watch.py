"""JobWatch (feature 056): what joins a running task with whoever may cancel its run. The client that starts a job in
another module says how to stop it; cancelling asks that module to stop after its current document, and a job not
started yet is never started."""

import threading
from collections.abc import Callable


class JobWatch:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop: Callable[[], None] | None = None
        self._cancelled = False

    @property
    def cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    def started(self, stop: Callable[[], None]) -> None:
        """A job started: `stop` asks its module to stop it. If the run was cancelled meanwhile, it is asked now."""
        with self._lock:
            self._stop = stop
            cancelled = self._cancelled
        if cancelled:
            stop()

    def ended(self) -> None:
        with self._lock:
            self._stop = None

    def cancel(self) -> None:
        """The run was cancelled: the job running now (if any) is asked to stop; none starts after this."""
        with self._lock:
            self._cancelled = True
            stop, self._stop = self._stop, None
        if stop is not None:
            stop()
