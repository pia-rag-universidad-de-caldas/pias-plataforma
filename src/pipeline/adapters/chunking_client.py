"""ChunkingClient: the routes of chunking (feature 043). Only sha256s and experiment ids go.

POST {chunking}/experiments {name, sha256s, chunking}   → 202 {id}; 409 while its line is full
GET  {chunking}/experiments/{id}                        → its status (queued, running, finished, failed...)
POST {chunking}/experiments/{id}/apply                  → its configuration becomes the active one
POST {chunking}/runs {sha256s}                          → 202 {id}: chunks with the active configuration (045)
GET  {chunking}/runs/{id}                               → its status and the sha256s chunked (`chunked`, the skipped
                                                          ones too); `partial` (some document failed) ends well
"""

import time
from collections.abc import Callable

import httpx

from pipeline.config import CHUNKING_EXPERIMENTS, CHUNKING_RUNS, EXPERIMENT_TIMEOUT, SUCCEEDED
from pipeline.models import ChunkingPort, JobOutcome, JsonObject, NotFoundError, json_list

from .http import segment
from .http.jobs import JobClient


class ChunkingClient(JobClient, ChunkingPort):
    done_keys = ("chunked", "sha256s")
    succeeded = SUCCEEDED | {"partial"}  # a run or an experiment where some document failed: go on with the rest

    def __init__(
        self,
        client: httpx.Client,
        path: str,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        timeout: float = EXPERIMENT_TIMEOUT,
    ) -> None:
        super().__init__(client, path, "chunking", sleep, clock, timeout)

    def experiment(self, body: JsonObject) -> JobOutcome:
        return self._job(CHUNKING_EXPERIMENTS, body)

    def apply(self, experiment: str) -> None:
        if self._request("POST", f"{CHUNKING_EXPERIMENTS}/{segment(experiment)}/apply") is None:
            raise NotFoundError(f"chunking has no experiment {experiment}")

    def promote(self, sha256s: list[str]) -> JobOutcome:
        deadline = self._clock() + self._timeout
        id = self._start(CHUNKING_RUNS, {"sha256s": json_list(sha256s), "simulate": False}, deadline)
        return self._wait(CHUNKING_RUNS, id, deadline)
