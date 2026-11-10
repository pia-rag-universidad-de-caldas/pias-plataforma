"""The processes that aren't in memory (they are read from another service), read at most every few seconds however
many are watching. Whoever asks never waits long: if that service is slow or down, they get the last ones known."""

import threading
import time
from collections.abc import Callable, Sequence

from .models import ProcessFacts

EVERY = 5.0  # seconds between two reads
PATIENCE = 1.0  # seconds a reader waits for a read in progress


class History:
    def __init__(
        self,
        read: Callable[[], Sequence[ProcessFacts]],
        errors: tuple[type[Exception], ...],
        every: float = EVERY,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._read, self._errors, self._every, self._clock = read, errors, every, clock
        self._lock = threading.Lock()
        self._known: tuple[ProcessFacts, ...] = ()
        self._problem: str | None = None
        self._read_at: float | None = None
        self._reading: threading.Thread | None = None

    def expire(self) -> None:
        """Something changed: read again next time."""
        with self._lock:
            self._read_at = None

    def _refresh(self) -> None:
        known, problem = self._known, None
        try:
            known = tuple(self._read())
        except self._errors as error:
            problem = str(error) or type(error).__name__
        with self._lock:
            self._known, self._problem, self._reading = known, problem, None
            self._read_at = self._clock()

    def current(self) -> tuple[tuple[ProcessFacts, ...], str | None]:
        with self._lock:
            stale = self._read_at is None or self._clock() - self._read_at >= self._every
            if stale and self._reading is None:
                self._reading = threading.Thread(target=self._refresh, name="process-history", daemon=True)
                self._reading.start()
            reading = self._reading
        if reading is not None:
            reading.join(PATIENCE)
        with self._lock:
            return self._known, self._problem
