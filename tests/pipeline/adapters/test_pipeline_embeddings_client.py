"""EmbeddingsClient against httpx.MockTransport: the contract of feature 044 (the module isn't merged yet)."""

import json
from collections.abc import Callable

import httpx
import pytest

from pipeline.adapters import EmbeddingsClient
from pipeline.models import EmbeddingModel, UnavailableError

type Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler) -> httpx.Client:
    return httpx.Client(base_url="http://server", transport=httpx.MockTransport(handler))


def test_models_are_read_with_their_limits() -> None:
    body = {"models": [{"name": "m", "default_tokens": 128, "max_tokens": 512, "default": True}]}
    models = EmbeddingsClient(_client(lambda _: httpx.Response(200, json=body)), "/embeddings").models()
    assert models == [EmbeddingModel("m", 128, 512, True)]


def test_a_malformed_model_is_unavailable() -> None:
    answer = httpx.Response(200, json=[{"name": "m"}])
    with pytest.raises(UnavailableError, match="without"):
        EmbeddingsClient(_client(lambda _: answer), "/embeddings").models()


def test_embed_sends_the_sha256s_and_waits() -> None:
    seen: list[tuple[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((f"{request.method} {request.url.path}", json.loads(request.content) if request.content else None))
        if request.method == "POST":
            return httpx.Response(202, json={"id": "v1", "status": "queued"})
        return httpx.Response(200, json={"id": "v1", "status": "finished", "embedded": ["a"]})

    outcome = EmbeddingsClient(_client(handler), "/embeddings", sleep=lambda _: None).embed(["a"])
    assert outcome.sha256s == ("a",) and outcome.succeeded
    assert seen == [("POST /embeddings/runs", {"sha256s": ["a"]}), ("GET /embeddings/runs/v1", None)]


def test_an_experiment_and_its_apply() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.method} {request.url.path}")
        if request.url.path.endswith("/apply"):
            return httpx.Response(200, json={})
        if request.method == "POST":
            return httpx.Response(202, json={"id": "e1"})
        return httpx.Response(200, json={"id": "e1", "status": "finished"})

    client = EmbeddingsClient(_client(handler), "/embeddings", sleep=lambda _: None)
    assert client.experiment({"chunking_experiment": "c1", "model": "m", "max_tokens": 128}).succeeded
    client.apply("e1")
    assert seen == [
        "POST /embeddings/experiments",
        "GET /embeddings/experiments/e1",
        "POST /embeddings/experiments/e1/apply",
    ]
