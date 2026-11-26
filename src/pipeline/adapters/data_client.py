"""DataClient: what the pipeline asks data directly: the JSON nodes (a production run with scope all) and, feature 062,
which parsed documents a selection takes and whether a chunking experiment ended (data says it, not chunking).

GET  {data}/nodes/JSON?page&per_page
POST {data}/documents/select {universe, files, exclude_experiment?, page, per_page}   → {total, sha256s, pages}
GET  {data}/nodes/EXPERIMENTO/{id}?omit=...                                           → its `estado` and `error`
"""

import time
from collections.abc import Callable

import httpx

from common.http import detail
from pipeline.config import DATA_EXPERIMENT, DATA_SELECT, EXPERIMENT_OMIT, EXPERIMENT_TIMEOUT, POLL_INTERVAL
from pipeline.models import (
    ActionError,
    DataPort,
    ExperimentState,
    IdPage,
    InvalidRequest,
    JobWatch,
    JsonObject,
    SelectedPage,
    UnavailableError,
)

from .http import BaseHttpClient, errors, segment
from .http.jobs import CANCELLED

JSON_NODES = "/nodes/JSON"
UNPROCESSABLE = 422
ALIVE = frozenset({"queued", "running"})  # the EXPERIMENTO's `estado` while chunking works on it


class DataClient(BaseHttpClient, DataPort):
    def __init__(
        self,
        client: httpx.Client,
        path: str,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        timeout: float = EXPERIMENT_TIMEOUT,
    ) -> None:
        super().__init__(client, path, errors("data"))
        self._sleep = sleep
        self._clock = clock
        self._timeout = timeout

    def json_page(self, page: int, per_page: int) -> IdPage:
        body = self._object(self._get(JSON_NODES, (("page", page), ("per_page", per_page))), "page of JSON nodes")
        try:
            return IdPage(tuple(str(n["id"]) for n in body["nodes"]), int(body["pages"]))
        except (KeyError, TypeError, ValueError) as e:
            raise UnavailableError(f"data answered a page of JSON nodes without nodes/pages: {e}") from e

    def select(
        self, universe: str, files: JsonObject, exclude_experiment: str | None, page: int, per_page: int
    ) -> SelectedPage:
        body: JsonObject = {"universe": universe, "files": files, "page": page, "per_page": per_page}
        if exclude_experiment is not None:
            body["exclude_experiment"] = exclude_experiment
        response = self._send("POST", DATA_SELECT, body=body)
        if response.status_code == UNPROCESSABLE:  # data says why the selection can't be taken
            raise InvalidRequest(f"data refused the selection: {detail(response)}")
        if not response.is_success:
            raise self._rejected("POST", DATA_SELECT, response)
        answer = self._object(self._json(response), "selection")
        try:
            sha256s = tuple(str(s) for s in answer["sha256s"])
            return SelectedPage(int(answer["total"]), sha256s, int(answer["pages"]))
        except (KeyError, TypeError, ValueError) as e:
            raise UnavailableError(f"data answered a selection without total/sha256s/pages: {e}") from e

    def _state(self, experiment: str) -> ExperimentState | None:
        params = tuple(("omit", key) for key in EXPERIMENT_OMIT)
        found = self._get(f"{DATA_EXPERIMENT}/{segment(experiment)}", params)
        if found is None:
            return None
        properties = self._object(found, f"EXPERIMENTO {experiment}").get("properties")
        if not isinstance(properties, dict):
            raise UnavailableError(f"data answered the EXPERIMENTO {experiment} without properties")
        error = properties.get("error")
        return ExperimentState(experiment, str(properties.get("estado") or ""), None if error is None else str(error))

    def wait_experiment(self, experiment: str, watch: JobWatch | None = None) -> ExperimentState:
        """Every POLL_INTERVAL until its `estado` isn't queued nor running (a node not written yet is waited for
        too), up to the timeout; a cancelled run stops waiting."""
        deadline = self._clock() + self._timeout
        while True:
            if watch is not None and watch.cancelled:
                raise ActionError(CANCELLED)
            state = self._state(experiment)
            if state is not None and state.status and state.status not in ALIVE:
                return state
            if self._clock() > deadline:
                raise UnavailableError(
                    f"the chunking experiment {experiment} is still running after {self._timeout:.0f}s"
                )
            self._sleep(POLL_INTERVAL)
