"""ChunkingClient: the experiment routes of chunking the stages use.

    POST {chunking}/experiments                   start one (409 while another one or a production run is running)
    GET  {chunking}/experiments/{id}              its status: running, finished, failed or interrupted
    POST {chunking}/experiments/{id}/scores       a score
    POST {chunking}/experiments/{id}/promote      its documents (or chunks) to the official graph

Chunking runs one experiment at a time: on 409 the client waits BUSY_RETRY and asks again, so a stage waits its turn
instead of failing; the executor's per-module queue already keeps the pipeline's own stages in line.
"""

import time
from collections.abc import Callable

import httpx

from pipeline.config import BUSY_RETRY, EXPERIMENT_TIMEOUT, POLL_INTERVAL
from pipeline.models import (
    ChunkingPort,
    ExperimentOutcome,
    JsonObject,
    NotFoundError,
    Promotion,
    UnavailableError,
)

from .http import CONFLICT, BaseHttpClient, segment

RUNNING = "running"


class ChunkingClient(BaseHttpClient, ChunkingPort):
    def __init__(
        self,
        client: httpx.Client,
        path: str,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        timeout: float = EXPERIMENT_TIMEOUT,
    ) -> None:
        super().__init__(client, path, "chunking")
        self._sleep = sleep
        self._clock = clock
        self._timeout = timeout

    def _start(self, body: JsonObject, deadline: float) -> str:
        while True:
            response = self._send("POST", "/experiments", body=body)
            if response.status_code != CONFLICT:
                break
            if self._clock() > deadline:
                raise UnavailableError(f"chunking stayed busy for {self._timeout:.0f}s")
            self._sleep(BUSY_RETRY)
        if not response.is_success:
            raise self._rejected("POST", "/experiments", response)
        id = self._object(self._json(response), "experiment").get("id")
        if not isinstance(id, str) or not id:
            raise UnavailableError(f"chunking started an experiment without id: {response.text[:300]}")
        return id

    def run_experiment(self, body: JsonObject) -> ExperimentOutcome:
        deadline = self._clock() + self._timeout
        id = self._start(body, deadline)
        while True:
            found = self._get(f"/experiments/{segment(id)}")
            if found is None:
                raise NotFoundError(f"the experiment {id} disappeared from chunking")
            view = self._object(found, "experiment")
            status = str(view.get("status"))
            if status != RUNNING:
                error = view.get("error")
                return ExperimentOutcome(id, status, None if error is None else str(error))
            if self._clock() > deadline:
                raise UnavailableError(f"the experiment {id} is still running after {self._timeout:.0f}s")
            self._sleep(POLL_INTERVAL)

    def score(self, experiment: str, score: JsonObject) -> None:
        if self._request("POST", f"/experiments/{segment(experiment)}/scores", body=score) is None:
            raise NotFoundError(f"chunking has no experiment {experiment}")

    def promote(self, experiment: str) -> Promotion:
        response = self._request("POST", f"/experiments/{segment(experiment)}/promote")
        if response is None:
            raise NotFoundError(f"chunking has no experiment {experiment}")
        body = self._object(self._json(response), "promotion")
        try:
            promoted = body["promoted"]
            failed = tuple((str(f["sha256"]), str(f["error"])) for f in body.get("failed") or [])
        except (KeyError, TypeError) as e:
            raise UnavailableError(f"chunking answered a promotion without promoted/failed: {e}") from e
        if isinstance(promoted, list):
            return Promotion(len(promoted), tuple(str(s) for s in promoted), failed)
        if isinstance(promoted, bool) or not isinstance(promoted, int):
            raise UnavailableError(f"chunking answered a promotion with promoted = {promoted!r}")
        return Promotion(promoted, None, failed)
