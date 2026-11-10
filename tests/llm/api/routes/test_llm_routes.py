"""The llm API on TestClient: data is a dict and Ollama a fake, both behind an httpx.MockTransport. The shapes are
those of the contract (spec/features/048-consultas-rag/contratos.md)."""

import time
from collections.abc import Iterator
from dataclasses import dataclass

import httpx
import pytest
from fakes import FakeData, FakeOllama
from fastapi.testclient import TestClient

from common.http import Json
from llm.adapters import HttpSession, OllamaClient
from llm.api import ApiSettings, create_app
from llm.config import DEFAULT_MODEL, MODELS

SMALL, VISION = "qwen2.5:0.5b", "qwen2.5vl:3b"
HELLO = {"messages": [{"role": "user", "content": "hola"}]}


@dataclass(frozen=True)
class FakeSettings(ApiSettings):
    data: FakeData | None = None
    fake_ollama: FakeOllama | None = None

    def session(self) -> HttpSession:
        assert self.data is not None
        return HttpSession(self.self_url, self.data_path, transport=httpx.MockTransport(self.data.handle))

    def ollama(self, timeout: float | None = None) -> OllamaClient:
        assert self.fake_ollama is not None
        return OllamaClient(self.ollama_url, transport=self.fake_ollama.transport())


@pytest.fixture
def ollama() -> FakeOllama:
    return FakeOllama()


@pytest.fixture
def client(fake_data: FakeData, ollama: FakeOllama) -> Iterator[TestClient]:
    settings = FakeSettings("http://server", data=fake_data, fake_ollama=ollama)
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def wait(client: TestClient, path: str) -> Json:
    for _ in range(300):
        found = client.get(path).json()
        if found["status"] in ("finished", "failed"):
            return found
        time.sleep(0.01)
    raise AssertionError(f"{path} didn't end")


# health and models


def test_health_says_ollama_and_its_version(client: TestClient, ollama: FakeOllama) -> None:
    found = client.get("/health").json()
    assert (found["ollama"], found["ollama_version"]) == ("ok", FakeOllama.VERSION)
    ollama.down = True
    found = client.get("/health").json()
    assert (found["status"], found["ollama"], found["ollama_version"]) == ("degraded", "unavailable", None)


def test_models_are_the_admitted_ones_and_what_ollama_has(client: TestClient, ollama: FakeOllama) -> None:
    ollama.models = {SMALL: 397, "other:7b": 4000}
    found = client.get("/models").json()
    admitted = {m["name"]: m for m in found["admitted"]}
    assert set(admitted) == set(MODELS)
    assert (
        admitted[SMALL]["installed"] and not admitted[DEFAULT_MODEL]["installed"] and admitted[DEFAULT_MODEL]["default"]
    )
    assert admitted[VISION]["vision"] and admitted[SMALL]["context"] == MODELS[SMALL].context
    assert [m["name"] for m in found["installed"]] == ["other:7b", SMALL]
    assert set(found["installed"][0]) == {"name", "size", "family", "modified"}


def test_models_without_ollama_is_503(client: TestClient, ollama: FakeOllama) -> None:
    ollama.down = True
    answer = client.get("/models")
    assert answer.status_code == 503 and "doesn't answer" in answer.json()["detail"]


# config


def test_config_is_the_default_until_someone_sets_it(client: TestClient, fake_data: FakeData) -> None:
    found = client.get("/config").json()
    assert (found["model"], found["origin"]) == (DEFAULT_MODEL, "defecto") and found["default"][
        "model"
    ] == DEFAULT_MODEL
    keys = {"model", "temperature", "num_ctx", "max_tokens", "system", "origin", "modified", "default"}
    assert set(found) == keys
    put = client.put("/config", json={"model": SMALL, "temperature": 0.5, "system": "Sé breve."}).json()
    assert (put["model"], put["temperature"], put["system"], put["origin"]) == (SMALL, 0.5, "Sé breve.", "manual")
    assert ("CONFIG_OFICIAL", "llm") in fake_data.nodes
    patched = client.patch("/config", json={"max_tokens": 64}).json()
    assert (patched["model"], patched["temperature"], patched["max_tokens"]) == (SMALL, 0.5, 64)
    assert client.get("/config").json()["max_tokens"] == 64
    assert client.delete("/config").json()["model"] == DEFAULT_MODEL
    assert ("CONFIG_OFICIAL", "llm") not in fake_data.nodes


@pytest.mark.parametrize(
    "body",
    [
        {"model": "gpt-4"},
        {"model": SMALL, "temperature": 3},
        {"model": SMALL, "num_ctx": 10**7},
        {"model": SMALL, "x": 1},
    ],
    ids=["not admitted", "hot", "context", "unknown key"],
)
def test_a_config_that_does_not_fit_is_422_and_nothing_is_written(
    client: TestClient, fake_data: FakeData, body: Json
) -> None:
    assert client.put("/config", json=body).status_code == 422
    assert fake_data.batches == []


def test_config_with_data_down_is_503(client: TestClient, fake_data: FakeData) -> None:
    fake_data.down = True
    assert client.get("/config").status_code == 503


# chat


def test_chat_uses_the_active_configuration(client: TestClient, ollama: FakeOllama) -> None:
    ollama.models = {SMALL: 1}
    client.put("/config", json={"model": SMALL, "temperature": 0.1, "system": "Sé breve."})
    answer = client.post("/chat", json=HELLO)
    assert answer.status_code == 200
    assert answer.json() == {
        "model": SMALL,
        "message": {"role": "assistant", "content": "eco: hola"},
        "prompt_tokens": 12,
        "answer_tokens": 3,
        "seconds": 1.5,
    }
    sent = ollama.chats[0]
    assert sent["messages"][0] == {"role": "system", "content": "Sé breve."}
    assert sent["options"]["temperature"] == 0.1


def test_chat_with_a_model_not_downloaded_is_503_with_the_pull(client: TestClient) -> None:
    answer = client.post("/chat", json={**HELLO, "model": SMALL})
    assert answer.status_code == 503 and f"ollama pull {SMALL}" in answer.json()["detail"]


def test_chat_without_ollama_is_503(client: TestClient, ollama: FakeOllama) -> None:
    ollama.down = True
    assert client.post("/chat", json={**HELLO, "model": SMALL}).status_code == 503


@pytest.mark.parametrize(
    "body",
    [
        {"messages": []},
        {**HELLO, "model": "gpt-4"},
        {**HELLO, "model": SMALL, "temperature": 5},
        {**HELLO, "model": SMALL, "max_tokens": 0},
        {"messages": [{"role": "user", "content": "¿qué ves?", "images": ["aGVsbG8="]}], "model": SMALL},
        {"messages": [{"role": "robot", "content": "x"}]},
        {**HELLO, "stream": True},
    ],
    ids=["no messages", "not admitted", "hot", "no answer", "image without vision", "unknown role", "unknown key"],
)
def test_a_chat_that_does_not_fit_is_422_and_ollama_is_not_asked(
    client: TestClient, ollama: FakeOllama, body: Json
) -> None:
    ollama.models = {SMALL: 1}
    assert client.post("/chat", json=body).status_code == 422
    assert ollama.chats == []


def test_images_reach_a_vision_model(client: TestClient, ollama: FakeOllama) -> None:
    ollama.models = {VISION: 1}
    body = {"messages": [{"role": "user", "content": "¿qué ves?", "images": ["aGVsbG8="]}], "model": VISION}
    assert client.post("/chat", json=body).status_code == 200
    assert ollama.chats[0]["messages"][-1]["images"] == ["aGVsbG8="]


# pulls and deletes


@pytest.mark.integration
def test_scenario_a_pull_runs_in_the_background_and_shows_in_processes(client: TestClient, ollama: FakeOllama) -> None:
    started = client.post("/models/pull", json={"name": SMALL})
    assert started.status_code == 202 and {"id", "status"} <= set(started.json())
    pull = wait(client, f"/models/pulls/{started.json()['id']}")
    assert (pull["status"], pull["model"], pull["completed"], pull["total"]) == ("finished", SMALL, 100, 100)
    assert SMALL in ollama.models and client.get("/models/pulls").json()[0]["id"] == pull["id"]
    processes = client.get("/processes").json()["processes"]
    assert [(p["module"], p["kind"], p["state"]) for p in processes] == [("llm", "pull", "finished")]


def test_a_pull_that_ollama_refuses_fails(client: TestClient, ollama: FakeOllama) -> None:
    ollama.pull_error = "file does not exist"
    pull = wait(client, f"/models/pulls/{client.post('/models/pull', json={'name': SMALL}).json()['id']}")
    assert pull["status"] == "failed" and "file does not exist" in pull["error"]


def test_pull_errors(client: TestClient, ollama: FakeOllama) -> None:
    assert client.post("/models/pull", json={"name": "gpt-4"}).status_code == 422
    assert client.get("/models/pulls/nope").status_code == 404
    ollama.down = True
    assert client.post("/models/pull", json={"name": SMALL}).status_code == 503
    assert client.get("/models/pulls").json() == []


def test_delete_a_model(client: TestClient, ollama: FakeOllama) -> None:
    ollama.models = {SMALL: 1, DEFAULT_MODEL: 2}
    assert client.delete(f"/models/{SMALL}").status_code == 204 and SMALL not in ollama.models
    assert client.delete(f"/models/{SMALL}").status_code == 404
    assert client.delete(f"/models/{DEFAULT_MODEL}").status_code == 409  # the active configuration's
    assert client.delete("/models/gpt-4").status_code == 422
