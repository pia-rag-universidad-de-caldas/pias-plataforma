"""EmbeddingsClient: the contract of feature 044 with the embeddings module (feature 046; its routes are the
constants of pipeline.config).

GET  {embeddings}/models                                        → [{name, default_tokens, max_tokens, default}]
POST {embeddings}/runs {sha256s}                                → 202 {id}: the official chunks, active configuration
GET  {embeddings}/runs/{id}                                     → its status and the sha256s it embedded (`embedded`)
POST {embeddings}/experiments {name, description, chunking_experiment, model, max_tokens} → 202 {id}
GET  {embeddings}/experiments/{id}                              → its status
POST {embeddings}/experiments/{id}/apply                        → its configuration becomes the active one
"""

import time
from collections.abc import Callable

import httpx

from pipeline.config import EMBEDDINGS_EXPERIMENTS, EMBEDDINGS_MODELS, EMBEDDINGS_RUNS, EXPERIMENT_TIMEOUT
from pipeline.models import (
    EmbeddingModel,
    EmbeddingsPort,
    JobOutcome,
    JsonObject,
    NotFoundError,
    UnavailableError,
    json_list,
)

from .http import Json, segment
from .http.jobs import JobClient


def _model(raw: Json) -> EmbeddingModel:
    if not isinstance(raw, dict):
        raise UnavailableError(f"embeddings answered a model that isn't an object: {raw!r}")
    try:
        name, default_tokens, max_tokens = raw["name"], raw["default_tokens"], raw["max_tokens"]
    except KeyError as e:
        raise UnavailableError(f"embeddings answered a model without {e}") from e
    if not isinstance(name, str) or not isinstance(default_tokens, int) or not isinstance(max_tokens, int):
        raise UnavailableError(f"embeddings answered a malformed model: {raw!r}")
    return EmbeddingModel(name, default_tokens, max_tokens, raw.get("default") is True)


class EmbeddingsClient(JobClient, EmbeddingsPort):
    done_keys = ("embedded", "sha256s")

    def __init__(
        self,
        client: httpx.Client,
        path: str,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        timeout: float = EXPERIMENT_TIMEOUT,
    ) -> None:
        super().__init__(client, path, "embeddings", sleep, clock, timeout)

    def models(self) -> list[EmbeddingModel]:
        found = self._get(EMBEDDINGS_MODELS)
        if found is None:
            raise UnavailableError(f"embeddings has no {self._path}{EMBEDDINGS_MODELS} route")
        items = found.get("models") if isinstance(found, dict) else found
        if not isinstance(items, list):
            raise UnavailableError(f"embeddings answered its models without a list: {str(found)[:300]}")
        return [_model(m) for m in items]

    def embed(self, sha256s: list[str]) -> JobOutcome:
        return self._job(EMBEDDINGS_RUNS, {"sha256s": json_list(sha256s)})

    def experiment(self, body: JsonObject) -> JobOutcome:
        return self._job(EMBEDDINGS_EXPERIMENTS, body)

    def apply(self, experiment: str) -> None:
        if self._request("POST", f"{EMBEDDINGS_EXPERIMENTS}/{segment(experiment)}/apply") is None:
            raise NotFoundError(f"embeddings has no experiment {experiment}")
