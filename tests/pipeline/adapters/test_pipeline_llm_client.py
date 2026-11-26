"""LlmClient against httpx.MockTransport: the contract of feature 048 with llm (the module isn't in this tree)."""

import json
from collections.abc import Callable

import httpx
import pytest

from pipeline.adapters import LlmClient
from pipeline.models import LlmModel, RejectedError, UnavailableError

type Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler) -> LlmClient:
    return LlmClient(httpx.Client(base_url="http://server", transport=httpx.MockTransport(handler)), "/llm")


def test_models_are_the_admitted_ones_with_whether_they_are_downloaded() -> None:
    body = {
        "admitted": [
            {"name": "qwen", "context": 8192, "vision": False, "installed": True, "default": True},
            {"name": "llava", "context": 4096, "vision": True, "installed": False, "default": False},
            {"name": "viejo"},  # without the flag: the `installed` list says it
        ],
        "installed": [{"name": "qwen", "size": 1}, {"name": "viejo", "size": 2}],
    }
    models = _client(lambda _: httpx.Response(200, json=body)).models()
    assert models == [
        LlmModel("qwen", 8192, False, True, True),
        LlmModel("llava", 4096, True, False, False),
        LlmModel("viejo", None, False, True, False),
    ]


def test_an_answer_without_admitted_is_unavailable() -> None:
    with pytest.raises(UnavailableError, match="admitted"):
        _client(lambda _: httpx.Response(200, json=[])).models()


def test_apply_puts_the_configuration() -> None:
    seen: list[tuple[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((f"{request.method} {request.url.path}", json.loads(request.content)))
        return httpx.Response(200, json={"model": "qwen"})

    _client(handler).apply({"model": "qwen", "temperature": 0.2})
    assert seen == [("PUT /llm/config", {"model": "qwen", "temperature": 0.2})]


@pytest.mark.parametrize(("status", "error"), [(422, RejectedError), (503, UnavailableError)])
def test_a_refused_or_failed_apply(status: int, error: type[Exception]) -> None:
    with pytest.raises(error):
        _client(lambda _: httpx.Response(status, json={"detail": "no"})).apply({"model": "qwen"})
