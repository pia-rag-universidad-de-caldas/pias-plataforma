"""Attachments of a question (feature 048, phase 2) on TestClient, with embeddings, llm, data and parsing as FakeModules
behind an httpx.MockTransport: a document searches by its pieces, an image by its description, and nothing of the
files is stored but their names."""

import base64
from collections.abc import Iterator

import pytest
from consultas_fakes import DESCRIPTION, FakeModules, admitted, hit
from fastapi.testclient import TestClient

from consultas.api import ApiSettings, create_app
from consultas.config import ATTACHMENT_QUESTION, DESCRIBE_PROMPT, MAX_ATTACHMENTS

PDF, PNG = b"%PDF-1.4 un plan", b"\x89PNG imagen"


def attached(name: str, content: bytes, mime: str | None = None) -> dict[str, str]:
    found = {"name": name, "content": base64.b64encode(content).decode()}
    if mime is not None:
        found["mime"] = mime
    return found


@pytest.fixture
def fake() -> FakeModules:
    return FakeModules()


@pytest.fixture
def client(fake: FakeModules) -> Iterator[TestClient]:
    with TestClient(create_app(ApiSettings("http://server"), fake.modules())) as test_client:
        yield test_client


def sent(fake: FakeModules, path: str) -> list[object]:
    return [body for _, at, body in fake.requests if at == path]


def test_a_document_searches_by_its_pieces_and_joins_them_by_best_score(client: TestClient, fake: FakeModules) -> None:
    fake.searches = [[hit("f1", 0.5), hit("f2", 0.4)], [hit("f1", 0.9), hit("f3", 0.6)]]
    answer = client.post("/ask", json={"attachments": [attached("plan.pdf", PDF)]})
    assert answer.status_code == 200
    found = answer.json()
    assert [(s["id"], s["score"]) for s in found["sources"]] == [("f1", 0.9), ("f3", 0.6), ("f2", 0.4)]
    [preview] = sent(fake, "/parsing/preview")
    assert isinstance(preview, dict) and preview["name"] == "plan.pdf" and preview["mime"] == "application/pdf"
    texts = [b for b in sent(fake, "/embeddings/vectors") if isinstance(b, dict) and len(b["texts"]) > 1]
    assert [b["texts"] for b in texts] == [["Evaluación\nDos parciales.", "Proyecto\nUna entrega."]]
    [use] = found["attachments"]
    assert (use["name"], use["kind"], use["pieces"], use["truncated"]) == ("plan.pdf", "documento", 2, False)


def test_the_question_is_the_default_one_without_text_and_only_names_are_stored(
    client: TestClient, fake: FakeModules
) -> None:
    fake.hits = [hit("f1", 0.8)]
    found = client.post("/ask", json={"attachments": [attached("plan.pdf", PDF)]}).json()
    stored = fake.nodes[("CONSULTA", found["consulta"])]
    assert stored["pregunta"] == ATTACHMENT_QUESTION
    assert (stored["adjuntos"], stored["tipos_adjuntos"], stored["trozos_busqueda"]) == (
        ["plan.pdf"],
        ["application/pdf"],
        2,
    )
    assert stored["caracteres_busqueda"] == len("Evaluación\nDos parciales.") + len("Proyecto\nUna entrega.")
    content = base64.b64encode(PDF).decode()
    assert not any(content in str(value) for node in fake.nodes.values() for value in node.values())
    chat = client.get(f"/chats/{found['chat']}").json()
    assert chat["questions"][0]["attachments"] == ["plan.pdf"]


def test_with_its_text_the_question_searches_too(client: TestClient, fake: FakeModules) -> None:
    fake.searches = [[hit("q1", 0.7)], [hit("f1", 0.6)], [hit("f2", 0.5)]]
    found = client.post("/search", json={"question": "evaluación", "attachments": [attached("plan.pdf", PDF)]}).json()
    assert [s["id"] for s in found] == ["q1", "f1", "f2"]
    assert not any(label in ("CHAT", "CONSULTA") for label, _ in fake.nodes)


def test_an_image_searches_by_what_the_vision_model_sees(client: TestClient, fake: FakeModules) -> None:
    fake.hits = [hit("f1", 0.8)]
    found = client.post("/ask", json={"question": "¿Y esto?", "attachments": [attached("foto.png", PNG)]}).json()
    describe, answer = sent(fake, "/llm/chat")
    assert isinstance(describe, dict) and describe["model"] == "qwen2.5vl:3b"
    assert describe["messages"] == [
        {"role": "user", "content": DESCRIBE_PROMPT, "images": [base64.b64encode(PNG).decode()]}
    ]
    texts = [b["texts"] for b in sent(fake, "/embeddings/vectors") if isinstance(b, dict)]
    assert [DESCRIPTION] in texts
    assert isinstance(answer, dict) and "images" not in answer["messages"][-1]  # qwen doesn't see images
    assert DESCRIPTION in answer["messages"][-1]["content"]
    assert found["attachments"][0]["description"] == DESCRIPTION


def test_the_image_goes_to_the_answer_if_its_model_sees(client: TestClient, fake: FakeModules) -> None:
    fake.hits, fake.active_model = [hit("f1", 0.8)], "qwen2.5vl:3b"
    client.post("/ask", json={"question": "¿Y esto?", "attachments": [attached("foto.png", PNG, "image/png")]})
    answer = sent(fake, "/llm/chat")[-1]
    assert isinstance(answer, dict) and answer["messages"][-1]["images"] == [base64.b64encode(PNG).decode()]


@pytest.mark.parametrize(
    "models",
    [[admitted("qwen"), admitted("qwen2.5vl:3b", vision=True, installed=False)], [admitted("qwen")]],
    ids=["not downloaded", "none admitted"],
)
def test_without_a_vision_model_an_image_is_503_saying_so(
    client: TestClient, fake: FakeModules, models: list[dict[str, object]]
) -> None:
    fake.models = models
    answer = client.post("/ask", json={"question": "a", "attachments": [attached("foto.png", PNG)]})
    assert answer.status_code == 503 and "vision model" in answer.json()["detail"]
    assert not any(label == "CONSULTA" for label, _ in fake.nodes)


def test_another_vision_model_downloaded_describes_it(client: TestClient, fake: FakeModules) -> None:
    fake.models = [admitted("qwen2.5vl:3b", vision=True, installed=False), admitted("llava", vision=True)]
    client.post("/search", json={"question": "a", "attachments": [attached("foto.png", PNG)]})
    describe = sent(fake, "/llm/chat")[0]
    assert isinstance(describe, dict) and describe["model"] == "llava"


@pytest.mark.parametrize(
    "attachments",
    [
        [attached("a.pdf", PDF)] * (MAX_ATTACHMENTS + 1),
        [attached("a.txt", b"texto")],
        [{"name": "a.pdf", "content": "no es base64!"}],
        [{"name": "a.pdf", "content": "eA==", "other": 1}],
    ],
    ids=["too many", "another type", "not base64", "unknown key"],
)
def test_wrong_attachments_are_422(client: TestClient, fake: FakeModules, attachments: list[object]) -> None:
    assert client.post("/ask", json={"question": "a", "attachments": attachments}).status_code == 422
    assert sent(fake, "/parsing/preview") == []


def test_without_question_nor_attachments_it_is_422(client: TestClient) -> None:
    assert client.post("/ask", json={}).status_code == 422


@pytest.mark.parametrize(("status", "code"), [(503, 503), (409, 503), (422, 422)], ids=["down", "busy", "unreadable"])
def test_parsing_failing_has_its_code(client: TestClient, fake: FakeModules, status: int, code: int) -> None:
    fake.preview_status = status
    answer = client.post("/ask", json={"attachments": [attached("plan.pdf", PDF)]})
    assert answer.status_code == code
    if code == 503:
        assert answer.json()["detail"].startswith("parsing is not answering")


def test_a_document_without_text_is_422(client: TestClient, fake: FakeModules) -> None:
    fake.preview = {**fake.preview, "sections": []}
    assert client.post("/ask", json={"attachments": [attached("plan.pdf", PDF)]}).status_code == 422
