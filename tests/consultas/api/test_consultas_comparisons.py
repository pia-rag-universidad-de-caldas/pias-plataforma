"""POST /compare and the stored comparisons (feature 060) on TestClient, with the modules as FakeModules: the panels
run in order, one failing doesn't stop the others, everything is checked first, the attachments are read once."""

import base64
from collections.abc import Iterator

import pytest
from consultas_fakes import FakeModules, admitted, hit
from fastapi.testclient import TestClient

from consultas.api import ApiSettings, create_app


@pytest.fixture
def fake() -> FakeModules:
    found = FakeModules(hits=[hit("f1", 0.8)])
    found.models = [admitted("qwen"), admitted("llama3.1:8b"), admitted("qwen2.5vl:3b", vision=True)]
    return found


@pytest.fixture
def client(fake: FakeModules) -> Iterator[TestClient]:
    with TestClient(create_app(ApiSettings("http://server"), fake.modules())) as test_client:
        yield test_client


def chats(fake: FakeModules) -> list[object]:
    """The model of each POST /llm/chat, in order."""
    return [body.get("model") for _, path, body in fake.requests if path == "/llm/chat" and isinstance(body, dict)]


TWO = [{"llm": {"model": "qwen"}}, {"label": "llama", "llm": {"model": "llama3.1:8b"}}]


def test_compare_answers_each_panel_in_order(client: TestClient, fake: FakeModules) -> None:
    found = client.post("/compare", json={"question": "¿Cómo se evalúa?", "panels": TWO}).json()
    assert [(p["index"], p["label"], p["status"]) for p in found["panels"]] == [
        (0, "Panel 1", "ok"),
        (1, "llama", "ok"),
    ]
    assert [p["answer"]["model"] for p in found["panels"]] == ["qwen", "llama3.1:8b"] == chats(fake)
    assert "chat" not in found["panels"][0]["answer"] and found["question"] == "¿Cómo se evalúa?"


def test_a_failing_panel_keeps_its_error_and_the_others_answer(client: TestClient, fake: FakeModules) -> None:
    fake.failing_llm_models = {"qwen"}
    found = client.post("/compare", json={"question": "a", "panels": TWO}).json()
    first, second = found["panels"]
    assert (first["status"], first["answer"]) == ("error", None) and first["error"].startswith("llm is not answering")
    assert second["status"] == "ok"
    stored = client.get(f"/comparisons/{found['comparison']}").json()
    assert [p["status"] for p in stored["panels"]] == ["error", "ok"]


def test_a_comparison_reads_back_as_it_was_answered(client: TestClient, fake: FakeModules) -> None:
    fake.nodes[("FRAGMENTOS", "f1")] = {"texto": "texto f1", "encabezados": ["Evaluación"], "paginas": [2]}
    panels = [{"against": {"embeddings_model": "m2"}, "k": 3}]
    answered = client.post("/compare", json={"question": "a", "panels": panels}).json()
    stored = client.get(f"/comparisons/{answered['comparison']}").json()
    assert stored == answered


def test_comparisons_are_listed_with_their_models(client: TestClient) -> None:
    id = client.post("/compare", json={"question": "a", "panels": TWO}).json()["comparison"]
    [listed] = client.get("/comparisons").json()
    assert listed == {
        "id": id,
        "question": "a",
        "created": listed["created"],
        "panels": 2,
        "models": ["qwen", "llama3.1:8b"],
    }


def test_deleting_a_comparison_takes_its_questions_not_the_chunks(client: TestClient, fake: FakeModules) -> None:
    fake.nodes[("FRAGMENTOS", "f1")] = {"texto": "uno"}
    id = client.post("/compare", json={"question": "a", "panels": TWO}).json()["comparison"]
    assert client.delete(f"/comparisons/{id}").status_code == 204
    assert set(fake.nodes) == {("FRAGMENTOS", "f1")}
    assert (
        client.get(f"/comparisons/{id}").status_code == 404 and client.delete(f"/comparisons/{id}").status_code == 404
    )


@pytest.mark.parametrize(
    "body",
    [
        {"question": "a", "panels": []},
        {"question": "a", "panels": [{}] * 5},
        {"question": "a", "panels": [{"model": "x"}]},
        {"question": "a", "panels": [{}], "chat": "c"},
        {"question": "a", "panels": [{"against": {}}]},
    ],
    ids=["no panels", "five panels", "unknown panel key", "unknown key", "empty against"],
)
def test_a_wrong_comparison_is_422(client: TestClient, body: dict[str, object]) -> None:
    assert client.post("/compare", json=body).status_code == 422


@pytest.mark.parametrize(
    ("panel", "code"),
    [
        ({"llm": {"model": "gpt-9"}}, 422),
        ({"against": {"embeddings_model": "nope"}}, 422),
        ({"against": {"embeddings_experiment": "nope"}}, 404),
        ({"against": {"embeddings_experiment": "e1"}}, 409),
    ],
    ids=["llm model", "embeddings model", "unknown experiment", "unfinished experiment"],
)
def test_every_panel_is_checked_before_any_runs(
    client: TestClient, fake: FakeModules, panel: dict[str, object], code: int
) -> None:
    fake.experiments["e1"] = {"id": "e1", "status": "running", "config": {"model": "m2", "max_tokens": 256}}
    found = client.post("/compare", json={"question": "a", "panels": [{}, panel]})
    assert found.status_code == code and chats(fake) == [] and fake.nodes == {}


def test_the_attachments_are_read_once_for_every_panel(client: TestClient, fake: FakeModules) -> None:
    attachments = [{"name": "plan.pdf", "content": base64.b64encode(b"%PDF un plan").decode()}]
    found = client.post("/compare", json={"question": "a", "attachments": attachments, "panels": TWO}).json()
    assert [p["status"] for p in found["panels"]] == ["ok", "ok"]
    assert len([path for _, path, _ in fake.requests if path == "/parsing/preview"]) == 1


def test_data_down_stops_the_comparison(client: TestClient, fake: FakeModules) -> None:
    fake.down = {"data"}
    found = client.post("/compare", json={"question": "a", "panels": TWO})
    assert found.status_code == 503 and found.json()["detail"].startswith("data is not answering")
