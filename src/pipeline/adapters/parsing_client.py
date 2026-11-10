"""ParsingClient: the routes of parsing (feature 042). Only sha256s go: parsing reads each file from its RAW node.

POST {parsing}/runs {sha256s?, redo, simulate} → 202 {id}; 409 while its line is full (no sha256s: all to parse)
GET  {parsing}/runs/{id}                      → its status and the sha256s it parsed (`parsed`)
"""

import time
from collections.abc import Callable

import httpx

from pipeline.config import EXPERIMENT_TIMEOUT, PARSING_RUNS
from pipeline.models import JobOutcome, JsonObject, ParsingPort, json_list

from .http.jobs import JobClient


class ParsingClient(JobClient, ParsingPort):
    done_keys = ("parsed", "sha256s")

    def __init__(
        self,
        client: httpx.Client,
        path: str,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        timeout: float = EXPERIMENT_TIMEOUT,
    ) -> None:
        super().__init__(client, path, "parsing", sleep, clock, timeout)

    def parse(self, sha256s: list[str]) -> JobOutcome:
        body: JsonObject = {"redo": False, "simulate": False}
        if sha256s:  # without them, parsing takes every current RAW still to parse
            body["sha256s"] = json_list(sha256s)
        return self._job(PARSING_RUNS, body)
