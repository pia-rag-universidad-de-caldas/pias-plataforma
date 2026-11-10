"""The admitted LLM models pulled in the background through /llm (feature 054), against a fake server."""

import json

import httpx

from server.console.bodies import JsonValue
from server.console.client import ApiClient
from server.console.model_pulls import ModelPulls, missing, progress

MODELS: JsonValue = {
    "admitted": [
        {"name": "qwen3:8b", "installed": True},
        {"name": "gemma3:4b", "installed": False},
        {"name": "llava:7b", "installed": False},
    ],
    "installed": [],
}


def puller(handler: httpx.MockTransport) -> ModelPulls:
    client = ApiClient(httpx.Client(base_url="http://server", transport=handler))
    return ModelPulls(client, sleep=lambda _: None)


def test_missing_are_the_admitted_not_installed() -> None:
    assert missing(MODELS) == ["gemma3:4b", "llava:7b"]
    assert missing(None) == [] and missing({"admitted": "x"}) == []


def test_progress_says_how_much_is_done() -> None:
    assert progress({"status": "pulling", "completed": 50, "total": 200}) == "pulling 25%"
    assert progress({"status": "pulling", "progress": 0.5}) == "pulling 50%"
    assert progress({"status": "queued"}) == "queued"


def test_each_missing_model_is_pulled_and_followed() -> None:
    pulled: list[str] = []
    looks: dict[str, int] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/llm/models":
            return httpx.Response(200, json=MODELS)
        if request.url.path == "/llm/models/pull":
            name = json.loads(request.content)["name"]
            pulled.append(name)
            return httpx.Response(202, json={"id": name, "status": "queued"})
        pull = request.url.path.rsplit("/", 1)[-1]
        looks[pull] = looks.get(pull, 0) + 1
        status = "done" if looks[pull] > 1 else "pulling"
        return httpx.Response(200, json={"id": pull, "status": status, "completed": 1, "total": 2})

    models = puller(httpx.MockTransport(handle))
    models.run()
    assert pulled == ["gemma3:4b", "llava:7b"]
    assert models.line == "modelos: 2 de 2 descargados"


def test_without_llm_nothing_is_pulled() -> None:
    sent: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        sent.append(f"{request.method} {request.url.path}")
        return httpx.Response(404, json={"detail": "Not Found"})

    models = puller(httpx.MockTransport(handle))
    models.run()
    assert sent == ["GET /llm/models"]
    assert "/llm no responde" in models.line


def test_a_failed_pull_is_counted() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/llm/models":
            return httpx.Response(200, json={"admitted": [{"name": "gemma3:4b", "installed": False}]})
        if request.url.path == "/llm/models/pull":
            return httpx.Response(202, json={"id": "1", "status": "queued"})
        return httpx.Response(200, json={"id": "1", "status": "failed", "error": "no space"})

    models = puller(httpx.MockTransport(handle))
    models.run()
    assert models.line == "modelos: 0 de 1 descargados; 1 no"
