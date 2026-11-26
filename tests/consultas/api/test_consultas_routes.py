"""The consultas API on TestClient: embeddings, llm and data are FakeModules behind an httpx.MockTransport."""

from collections.abc import Iterator

import pytest
from consultas_fakes import FakeModules, hit
from fastapi.testclient import TestClient

from consultas.api import ApiSettings, create_app
from consultas.config import NOT_FOUND, PROMPT


@pytest.fixture
def fake() -> FakeModules:
    return FakeModules()


@pytest.fixture
def client(fake: FakeModules) -> Iterator[TestClient]:
    with TestClient(create_app(ApiSettings("http://server"), fake.modules())) as test_client:
        yield test_client


def test_ask_answers_with_its_sources_and_stores_the_chat(client: TestClient, fake: FakeModules) -> None:
    fake.hits = [hit("f1", 0.8), hit("f2", 0.1)]
    answer = client.post("/ask", json={"question": "¿Cómo se evalúa?"})
    assert answer.status_code == 200
    found = answer.json()
    assert set(found) >= {"answer", "sources", "chat", "consulta", "model", "found", "seconds"}
    assert (found["answer"], found["model"], found["found"]) == (fake.reply, "qwen", True)
    assert [s["id"] for s in found["sources"]] == ["f1"] and set(found["seconds"]) == {"search", "answer"}
    chat = client.get(f"/chats/{found['chat']}").json()
    [question] = chat["questions"]
    assert (question["question"], question["answer"], question["llm_model"]) == ("¿Cómo se evalúa?", fake.reply, "qwen")
    assert [(s["id"], s["order"], s["score"]) for s in question["sources"]] == [("f1", 1, 0.8)]


def test_ask_without_context_does_not_call_the_llm(client: TestClient, fake: FakeModules) -> None:
    found = client.post("/ask", json={"question": "a"}).json()
    assert (found["answer"], found["found"], found["model"]) == (NOT_FOUND, False, None)
    assert not any(path.startswith("/llm") for _, path, _ in fake.requests)


def test_a_chat_goes_on_with_its_history(client: TestClient, fake: FakeModules) -> None:
    fake.hits = [hit("f1", 0.8)]
    first = client.post("/ask", json={"question": "primera"}).json()
    second = client.post("/ask", json={"question": "segunda", "chat": first["chat"]}).json()
    assert second["chat"] == first["chat"]
    _, _, body = [r for r in fake.requests if r[1] == "/llm/chat"][-1]
    assert isinstance(body, dict)
    assert [m["content"] for m in body["messages"][:2]] == ["primera", fake.reply]
    assert len(client.get(f"/chats/{first['chat']}").json()["questions"]) == 2


@pytest.mark.parametrize("service", ["embeddings", "llm", "data"])
def test_a_module_down_is_503_saying_which_and_nothing_is_stored(
    client: TestClient, fake: FakeModules, service: str
) -> None:
    fake.hits = [hit("f1", 0.8)]
    fake.down = {service}
    answer = client.post("/ask", json={"question": "a"})
    assert answer.status_code == 503 and answer.json()["detail"].startswith(f"{service} is not answering")
    assert not any(label == "CONSULTA" for label, _ in fake.nodes)


def test_llm_refusing_the_overrides_is_422(client: TestClient, fake: FakeModules) -> None:
    fake.hits, fake.llm_refuses = [hit("f1", 0.8)], True
    assert client.post("/ask", json={"question": "a", "llm": {"model": "x"}}).status_code == 422


def test_the_llm_overrides_go_to_llm(client: TestClient, fake: FakeModules) -> None:
    fake.hits = [hit("f1", 0.8)]
    found = client.post("/ask", json={"question": "a", "llm": {"model": "otro", "temperature": 0.1}}).json()
    _, _, body = [r for r in fake.requests if r[1] == "/llm/chat"][-1]
    assert isinstance(body, dict) and (body["model"], body["temperature"]) == ("otro", 0.1) and found["model"] == "otro"


def test_against_searches_the_experiment_and_is_laboratory(client: TestClient, fake: FakeModules) -> None:
    fake.experiments["e1"] = {"id": "e1", "status": "finished", "config": {"model": "m2", "max_tokens": 256}}
    fake.hits = [hit("c1", 0.9)]
    found = client.post("/ask", json={"question": "a", "against": {"embeddings_experiment": "e1"}}).json()
    _, _, search = [r for r in fake.requests if r[1] == "/data/vectors/search"][-1]
    assert isinstance(search, dict) and (search["index"], search["experiment"]) == ("vec_exp_chunk_m_2", "e1")
    assert found["laboratory"] and ("RESPONDIDA_CON", "CONSULTA", found["consulta"], "EXP_CHUNK", "c1") in fake.links


def test_against_an_unknown_experiment_is_404(client: TestClient) -> None:
    body = {"question": "a", "against": {"embeddings_experiment": "nope"}}
    assert client.post("/ask", json=body).status_code == 404


@pytest.mark.parametrize(
    "against",
    [{}, {"embeddings_experiment": "e1", "embeddings_model": "m2"}, {"index": "x"}],
    ids=["none", "both", "unknown key"],
)
def test_against_takes_exactly_one_target(client: TestClient, against: dict[str, str]) -> None:
    assert client.post("/search", json={"question": "a", "against": against}).status_code == 422


def test_against_an_embeddings_model_searches_its_official_index(client: TestClient, fake: FakeModules) -> None:
    fake.hits = [hit("f1", 0.8)]
    found = client.post("/ask", json={"question": "a", "against": {"embeddings_model": "m2"}}).json()
    _, _, vectors = [r for r in fake.requests if r[1] == "/embeddings/vectors"][-1]
    _, _, search = [r for r in fake.requests if r[1] == "/data/vectors/search"][-1]
    assert isinstance(vectors, dict) and vectors["model"] == "m2" and "max_tokens" not in vectors
    assert isinstance(search, dict) and "experiment" not in search and not found["laboratory"]


def test_an_embeddings_model_embeddings_does_not_serve_is_422(client: TestClient, fake: FakeModules) -> None:
    fake.refused_models = {"nope"}
    assert client.post("/search", json={"question": "a", "against": {"embeddings_model": "nope"}}).status_code == 422


def test_an_embeddings_model_without_vectors_finds_nothing(client: TestClient, fake: FakeModules) -> None:
    fake.hits, fake.indexes = [hit("f1", 0.8)], {"m2": "vec_fragmentos_m2_3"}  # data has no such index
    found = client.post("/ask", json={"question": "a", "against": {"embeddings_model": "m2"}})
    assert found.status_code == 200 and (found.json()["found"], found.json()["sources"]) == (False, [])


def test_search_answers_the_chunks_without_llm_nor_storing(client: TestClient, fake: FakeModules) -> None:
    fake.hits = [hit("f1", 0.8), hit("f2", 0.1)]
    found = client.post("/search", json={"question": "a", "k": 2}).json()
    assert [s["id"] for s in found] == ["f1", "f2"] and set(found[0]) == set(hit("f1", 0.8))
    assert not any(label in ("CHAT", "CONSULTA") for label, _ in fake.nodes)


def test_search_before_any_index_finds_nothing(client: TestClient, fake: FakeModules) -> None:
    fake.experiments["e1"] = {"id": "e1", "status": "finished", "config": {"model": "m", "max_tokens": 128}}
    assert client.post("/search", json={"question": "a"}).json() == []


@pytest.mark.parametrize(
    "body",
    [{"question": ""}, {"question": "a", "k": 0}, {"question": "a", "index": "x"}, {"question": "a", "llm": {"x": 1}}],
    ids=["empty", "k", "unknown key", "unknown llm key"],
)
def test_a_wrong_question_is_422(client: TestClient, body: dict[str, object]) -> None:
    assert client.post("/ask", json=body).status_code == 422


def test_an_unknown_chat_is_404(client: TestClient) -> None:
    assert client.post("/ask", json={"question": "a", "chat": "nope"}).status_code == 404
    assert client.get("/chats/nope").status_code == 404
    assert client.delete("/chats/nope").status_code == 404


def test_chats_are_listed_and_deleted_with_their_questions(client: TestClient, fake: FakeModules) -> None:
    fake.hits = [hit("f1", 0.8)]
    fake.nodes[("FRAGMENTOS", "f1")] = {"texto": "uno"}
    chat = client.post("/ask", json={"question": "¿Cómo se evalúa?"}).json()["chat"]
    [listed] = client.get("/chats").json()
    assert (listed["id"], listed["title"], listed["laboratory"]) == (chat, "¿Cómo se evalúa?", False)
    assert client.delete(f"/chats/{chat}").status_code == 204
    assert set(fake.nodes) == {("FRAGMENTOS", "f1")}  # the chunk stays


def test_config_defaults_changes_and_goes_back(client: TestClient) -> None:
    found = client.get("/config").json()
    assert (found["k"], found["prompt"], found["origin"]) == (5, PROMPT, "defecto")
    assert client.patch("/config", json={"k": 8}).json()["k"] == 8
    assert client.get("/config").json()["k"] == 8
    assert client.put("/config", json={"min_score": 0.5}).json()["k"] == 5
    assert client.delete("/config").json()["origin"] == "defecto"


def test_a_prompt_without_its_marks_is_422(client: TestClient) -> None:
    assert client.put("/config", json={"prompt": "sin marcas"}).status_code == 422


def test_the_configured_k_is_the_one_searched(client: TestClient, fake: FakeModules) -> None:
    client.patch("/config", json={"k": 7})
    client.post("/search", json={"question": "a"})
    _, _, search = [r for r in fake.requests if r[1] == "/data/vectors/search"][-1]
    assert isinstance(search, dict) and search["k"] == 7


def test_health_says_which_module_does_not_answer(client: TestClient) -> None:
    found = client.get("/health").json()  # nothing listens at http://server
    assert (found["status"], found["llm"], found["data"], found["parsing"]) == ("degraded",) + ("unavailable",) * 3
