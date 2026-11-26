"""ChunkingClient: the routes of chunking (feature 043). Only sha256s and experiment ids go.

POST {chunking}/experiments {name, sha256s, chunking}   → 202 {id}; 409 while its line is full
GET  {chunking}/experiments/{id}                        → its status (queued, running, finished, failed...) and the
                                                          parameters it chunks with (`chunking`)
POST {chunking}/experiments/{id}/apply                  → its configuration becomes the active one
POST {chunking}/experiments/{id}/documents {sha256s}    → 202 {added, already, unparsed, total} (feature 062)
POST {chunking}/experiments/{id}/resume                 → a partial, failed or interrupted experiment back in line
GET  {chunking}/config                                  → the active configuration (`chunking`: its parameters)
POST {chunking}/runs {sha256s}                          → 202 {id}: chunks with the active configuration (045)
GET  {chunking}/runs/{id}                               → its status and the sha256s chunked (`chunked`, the skipped
                                                          ones too); `partial` (some document failed) ends well
POST {chunking}/runs/{id}/cancel                        → it stops after its current document (feature 056)
"""

import time
from collections.abc import Callable

import httpx

from pipeline.config import CHUNKING_CONFIG, CHUNKING_EXPERIMENTS, CHUNKING_RUNS, EXPERIMENT_TIMEOUT, SUCCEEDED
from pipeline.models import (
    AddedDocuments,
    ChunkingExperimentInfo,
    ChunkingPort,
    JobOutcome,
    JobWatch,
    JsonObject,
    NotFoundError,
    UnavailableError,
    json_list,
)

from .http import Json, segment
from .http.jobs import JobClient


def _count(body: Json, key: str) -> int:
    value = body.get(key) if isinstance(body, dict) else None
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


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

    def experiment(self, body: JsonObject, watch: JobWatch | None = None) -> JobOutcome:
        return self._job(CHUNKING_EXPERIMENTS, body, watch)

    def apply(self, experiment: str) -> None:
        if self._request("POST", f"{CHUNKING_EXPERIMENTS}/{segment(experiment)}/apply") is None:
            raise NotFoundError(f"chunking has no experiment {experiment}")

    def promote(self, sha256s: list[str], watch: JobWatch | None = None) -> JobOutcome:
        return self._job(CHUNKING_RUNS, {"sha256s": json_list(sha256s), "simulate": False}, watch, stoppable=True)

    def start_experiment(self, body: JsonObject, watch: JobWatch | None = None) -> str:
        return self._start(CHUNKING_EXPERIMENTS, body, self._deadline(), watch)

    def experiment_info(self, experiment: str) -> ChunkingExperimentInfo | None:
        found = self._get(f"{CHUNKING_EXPERIMENTS}/{segment(experiment)}")
        if found is None:
            return None
        view = self._object(found, f"experiment {experiment}")
        status, chunking = view.get("status"), view.get("chunking")
        if not isinstance(status, str):
            raise UnavailableError(f"chunking answered the experiment {experiment} without a status")
        return ChunkingExperimentInfo(experiment, status, dict(chunking) if isinstance(chunking, dict) else {})

    def add_documents(self, experiment: str, sha256s: list[str], watch: JobWatch | None = None) -> AddedDocuments:
        route = f"{CHUNKING_EXPERIMENTS}/{segment(experiment)}/documents"
        body: JsonObject = {"sha256s": json_list(sha256s), "simulate": False}
        answer = self._json(self._post_waiting(route, body, self._deadline(), watch))
        return AddedDocuments(
            _count(answer, "added"), _count(answer, "already"), _count(answer, "unparsed"), _count(answer, "total")
        )

    def resume_experiment(self, experiment: str, watch: JobWatch | None = None) -> None:
        self._post_waiting(f"{CHUNKING_EXPERIMENTS}/{segment(experiment)}/resume", None, self._deadline(), watch)

    def config(self) -> JsonObject | None:
        found = self._object(self._get(CHUNKING_CONFIG), "configuration")
        chunking = found.get("chunking")
        return dict(chunking) if isinstance(chunking, dict) else None
