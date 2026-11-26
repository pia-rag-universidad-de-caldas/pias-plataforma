"""JobClient: starting something another module runs in the background and waiting for it to end.

    POST {module}{route}           202 with its `id`; a 409 (its line is full, or another one runs) is waited out
    GET  {module}{route}/{id}      until its status isn't alive any more (polled every POLL_INTERVAL)

Every module answers its own words for the status (ingesta, `estado`: en_curso/terminada/fallida; the others,
`status`: queued/running/finished...): the subclass says which field and which values.

With a JobWatch (feature 056), a cancelled run starts nothing (not even after a 409), and a job that has a cancel
route (POST {module}{route}/{id}/cancel: parsing, chunking and embeddings runs) is asked to stop after its current
document; the client keeps waiting until it ends.
"""

import logging
import time
from collections.abc import Callable, Collection, Mapping

import httpx

from common.http import CONFLICT, NOT_FOUND, BaseHttpClient, Json, detail, segment
from pipeline.config import ALIVE, BUSY_RETRY, EXPERIMENT_TIMEOUT, POLL_INTERVAL, SUCCEEDED
from pipeline.models import (
    ActionError,
    JobOutcome,
    JobWatch,
    JsonObject,
    NotFoundError,
    PipelineError,
    UnavailableError,
)

from .policy import errors

LOG = logging.getLogger(__name__)
CANCELLED = "the run was cancelled: nothing more is launched"


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

    def _deadline(self) -> float:
        return self._clock() + self._timeout

    def _post_waiting(
        self, route: str, body: JsonObject | None, deadline: float, watch: JobWatch | None = None
    ) -> httpx.Response:
        """A successful POST, waiting out a 409 (the module's line is full) every BUSY_RETRY; a 404 is
        NotFoundError and any other 4xx RejectedError. A cancelled run sends nothing."""
        while True:
            if watch is not None and watch.cancelled:
                raise ActionError(CANCELLED)
            response = self._send("POST", route, body=body)
            if response.status_code != CONFLICT:
                break
            if self._clock() > deadline:
                raise UnavailableError(f"{self._service} stayed busy for {self._timeout:.0f}s")
            self._sleep(BUSY_RETRY)
        if response.status_code == NOT_FOUND:
            raise NotFoundError(f"{self._service}: {detail(response)}")
        if not response.is_success:
            raise self._rejected("POST", route, response)
        return response

    def _start(self, route: str, body: JsonObject, deadline: float, watch: JobWatch | None = None) -> str:
        response = self._post_waiting(route, body, deadline, watch)
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

    def _stop(self, route: str, id: str) -> None:
        """Asks the module to stop job `id` after its current document; a failure is only logged (the job then ends
        on its own, and its result is dropped)."""
        try:
            response = self._send("POST", f"{route}/{segment(id)}/cancel")
        except PipelineError as e:
            LOG.warning("%s %s couldn't be asked to stop: %s", self._service, id, e)
            return
        if not response.is_success and response.status_code != CONFLICT:  # 409: it had already ended
            LOG.warning("%s %s couldn't be asked to stop: %s", self._service, id, response.status_code)

    def _job(self, route: str, body: JsonObject, watch: JobWatch | None = None, stoppable: bool = False) -> JobOutcome:
        """Starts it and waits until it ends; `stoppable`: the module has a cancel route for it."""
        deadline = self._clock() + self._timeout
        id = self._start(route, body, deadline, watch)
        if watch is None:
            return self._wait(route, id, deadline)
        if stoppable:
            watch.started(lambda: self._stop(route, id))
        try:
            return self._wait(route, id, deadline)
        finally:
            watch.ended()
