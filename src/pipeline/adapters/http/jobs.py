"""JobClient: starting something another module runs in the background and waiting for it to end.

    POST {module}{route}           202 with its `id`; a 409 (its line is full, or another one runs) is waited out
    GET  {module}{route}/{id}      until its status isn't alive any more (polled every POLL_INTERVAL)

Every module answers its own words for the status (ingesta, `estado`: en_curso/terminada/fallida; the others,
`status`: queued/running/finished...): the subclass says which field and which values.
"""

import time
from collections.abc import Callable, Collection, Mapping

import httpx

from common.http import CONFLICT, BaseHttpClient, Json, segment
from pipeline.config import ALIVE, BUSY_RETRY, EXPERIMENT_TIMEOUT, POLL_INTERVAL, SUCCEEDED
from pipeline.models import JobOutcome, JsonObject, NotFoundError, UnavailableError

from .policy import errors


def texts(view: Mapping[str, Json], keys: tuple[str, ...]) -> tuple[str, ...]:
    """The first of `keys` that holds a list, as texts (the sha256s a job says it did); () if none does."""
    for key in keys:
        value = view.get(key)
        if isinstance(value, list):
            return tuple(str(v.get("sha256") if isinstance(v, dict) else v) for v in value)
    return ()


class JobClient(BaseHttpClient):
    status_field = "status"
    alive: Collection[str] = ALIVE
    succeeded: Collection[str] = SUCCEEDED
    done_keys: tuple[str, ...] = ("sha256s",)  # where the job lists what it did

    def __init__(
        self,
        client: httpx.Client,
        path: str,
        service: str,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        timeout: float = EXPERIMENT_TIMEOUT,
    ) -> None:
        super().__init__(client, path, errors(service))
        self._service = service
        self._sleep = sleep
        self._clock = clock
        self._timeout = timeout

    def _start(self, route: str, body: JsonObject, deadline: float) -> str:
        while True:
            response = self._send("POST", route, body=body)
            if response.status_code != CONFLICT:
                break
            if self._clock() > deadline:
                raise UnavailableError(f"{self._service} stayed busy for {self._timeout:.0f}s")
            self._sleep(BUSY_RETRY)
        if not response.is_success:
            raise self._rejected("POST", route, response)
        id = self._object(self._json(response), f"answer of POST {route}").get("id")
        if not isinstance(id, str) or not id:
            raise UnavailableError(f"{self._service} started something without id: {response.text[:300]}")
        return id

    def _wait(self, route: str, id: str, deadline: float) -> JobOutcome:
        while True:
            found = self._get(f"{route}/{segment(id)}")
            if found is None:
                raise NotFoundError(f"{id} disappeared from {self._service}")
            view = self._object(found, f"{route}/{id}")
            status = str(view.get(self.status_field))
            if status not in self.alive:
                error = view.get("error")
                return JobOutcome(
                    id,
                    status,
                    None if error is None else str(error),
                    texts(view, self.done_keys),
                    status in self.succeeded,
                )
            if self._clock() > deadline:
                raise UnavailableError(f"{id} of {self._service} is still running after {self._timeout:.0f}s")
            self._sleep(POLL_INTERVAL)

    def _job(self, route: str, body: JsonObject) -> JobOutcome:
        """Starts it and waits until it ends."""
        deadline = self._clock() + self._timeout
        return self._wait(route, self._start(route, body, deadline), deadline)
