"""EmbeddingsClient: the contract of feature 044 with the embeddings module (feature 046; its routes are the
constants of pipeline.config).

GET  {embeddings}/models                → [{name, default_tokens, max_tokens, default, passage_budget,
                                           default_passage_budget, official_passage_budget}] (budgets: feature 062)
POST {embeddings}/runs {sha256s, model?}                        → 202 {id}: the official chunks (the active model, or
                                                                  another next to it)
GET  {embeddings}/runs/{id}                                     → its status and the sha256s it embedded (`embedded`)
POST {embeddings}/runs/{id}/cancel                              → it stops after its current document (feature 056)
POST {embeddings}/experiments {name, description, chunking_experiment, model, max_tokens} → 202 {id}
GET  {embeddings}/experiments?chunking_experiment=              → those over that chunking experiment (feature 059)
GET  {embeddings}/experiments/{id}                              → its status (and `pending`, feature 062)
POST {embeddings}/experiments/{id}/resume                       → embeds what it lacks (feature 062)
POST {embeddings}/experiments/{id}/apply                        → its configuration becomes the active one
"""

import time
from collections.abc import Callable

import httpx

from pipeline.config import EMBEDDINGS_EXPERIMENTS, EMBEDDINGS_MODELS, EMBEDDINGS_RUNS, EXPERIMENT_TIMEOUT
from pipeline.models import (
    EmbeddingModel,
    EmbeddingsExperimentInfo,
    EmbeddingsPort,
    JobOutcome,
    JobWatch,
    JsonObject,
    NotFoundError,
    UnavailableError,
    json_list,
)

from .http import CONFLICT, Json, segment
from .http.jobs import JobClient

_BUDGETS = ("passage_budget", "default_passage_budget", "official_passage_budget")


def _budget(raw: dict[str, Json], key: str) -> int | None:
    value = raw.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _model(raw: Json) -> EmbeddingModel:
    if not isinstance(raw, dict):
        raise UnavailableError(f"embeddings answered a model that isn't an object: {raw!r}")
    try:
        name, default_tokens, max_tokens = raw["name"], raw["default_tokens"], raw["max_tokens"]
    except KeyError as e:
        raise UnavailableError(f"embeddings answered a model without {e}") from e
    if not isinstance(name, str) or not isinstance(default_tokens, int) or not isinstance(max_tokens, int):
        raise UnavailableError(f"embeddings answered a malformed model: {raw!r}")
    passage, default, official = (_budget(raw, key) for key in _BUDGETS)
    return EmbeddingModel(name, default_tokens, max_tokens, raw.get("default") is True, passage, default, official)


def _pending(view: dict[str, Json]) -> int | None:
    value = view.get("pending")
    if isinstance(value, list):
        return len(value)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _info(raw: Json) -> EmbeddingsExperimentInfo:
    if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
        raise UnavailableError(f"embeddings answered an experiment without id: {str(raw)[:300]}")
    model = raw.get("model")
    if not isinstance(model, str):
        config = raw.get("config")
        model = config.get("model") if isinstance(config, dict) else None
    return EmbeddingsExperimentInfo(raw["id"], str(model or ""), str(raw.get("status")), _pending(raw))


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

    def embed(self, sha256s: list[str], watch: JobWatch | None = None) -> JobOutcome:
        return self._job(EMBEDDINGS_RUNS, {"sha256s": json_list(sha256s)}, watch, stoppable=True)

    def experiment(self, body: JsonObject, watch: JobWatch | None = None) -> JobOutcome:
        return self._job(EMBEDDINGS_EXPERIMENTS, body, watch)

    def apply(self, experiment: str) -> None:
        if self._request("POST", f"{EMBEDDINGS_EXPERIMENTS}/{segment(experiment)}/apply") is None:
            raise NotFoundError(f"embeddings has no experiment {experiment}")

    def experiments_of(self, chunking_experiment: str) -> list[EmbeddingsExperimentInfo]:
        found = self._get(EMBEDDINGS_EXPERIMENTS, (("chunking_experiment", chunking_experiment),))
        if not isinstance(found, list):
            raise UnavailableError(f"embeddings answered its experiments without a list: {str(found)[:300]}")
        return [_info(item) for item in found]

    def resume(self, experiment: str, watch: JobWatch | None = None) -> JobOutcome:
        route = f"{EMBEDDINGS_EXPERIMENTS}/{segment(experiment)}"
        deadline = self._deadline()
        found = self._get(route)
        if found is None:
            raise NotFoundError(f"embeddings has no experiment {experiment}")
        info = _info(found)
        if info.status in self.alive or info.pending == 0:  # running: only waited for; lacking nothing: done
            return self._wait(EMBEDDINGS_EXPERIMENTS, experiment, deadline)
        if info.pending is not None:  # it lacks something: a 409 is its full line, waited out
            self._post_waiting(f"{route}/resume", {}, deadline, watch)
        else:  # it doesn't say: a 409 may be "nothing lacking" as well, so it isn't retried
            response = self._send("POST", f"{route}/resume", body={})
            if not response.is_success and response.status_code != CONFLICT:
                raise self._rejected("POST", f"{route}/resume", response)
        return self._wait(EMBEDDINGS_EXPERIMENTS, experiment, deadline)

    def embed_model(self, sha256s: list[str], model: str, watch: JobWatch | None = None) -> JobOutcome:
        return self._job(EMBEDDINGS_RUNS, {"sha256s": json_list(sha256s), "model": model}, watch, stoppable=True)
