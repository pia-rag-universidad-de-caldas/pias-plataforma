"""The HTTP clients of consultas over httpx.MockTransport: the contracts of embeddings, llm and data, and what an
answer of another shape becomes."""

import httpx
import pytest

from consultas.adapters import DataClient, EmbeddingsClient, LlmClient, batch_body, chat_body
from consultas.models import (
    DataDown,
    EmbeddingsDown,
    GraphBatch,
    GraphLabel,
    GraphNode,
    InvalidQuestion,
    LlmDown,
    LlmOptions,
    Message,
    NodeKey,
    Rejected,
    Role,
)


def http(status: int, body: object) -> httpx.Client:
    return httpx.Client(
        base_url="http://server", transport=httpx.MockTransport(lambda _: httpx.Response(status, json=body))
    )


def test_the_chat_body_leaves_out_what_is_not_overridden() -> None:
    body = chat_body([Message(Role.USER, "hola")], LlmOptions(temperature=0.2))
    assert body == {"messages": [{"role": "user", "content": "hola"}], "temperature": 0.2}


def test_a_reply_is_read_as_the_contract_says() -> None:
    answer = {
        "model": "qwen",
        "message": {"role": "assistant", "content": "sí"},
        "prompt_tokens": 4,
        "answer_tokens": 1,
    }
    reply = LlmClient(http(200, answer), "/llm").chat([Message(Role.USER, "a")], LlmOptions())
    assert (reply.model, reply.content, reply.prompt_tokens, reply.seconds) == ("qwen", "sí", 4, None)


@pytest.mark.parametrize(
    ("status", "body", "error"),
    [
        (503, {"detail": "Ollama doesn't answer"}, LlmDown),
        (404, {"detail": "Not Found"}, LlmDown),  # no llm module in the server
        (422, {"detail": "not admitted"}, InvalidQuestion),
        (200, {"model": "qwen"}, LlmDown),  # another shape
    ],
    ids=["down", "no route", "refused", "malformed"],
)
def test_what_llm_answers_wrong(status: int, body: object, error: type[Exception]) -> None:
    with pytest.raises(error):
        LlmClient(http(status, body), "/llm").chat([Message(Role.USER, "a")], LlmOptions())


def test_a_question_vector_must_have_the_dimensions_of_its_model() -> None:
    body = {"model": "m", "max_tokens": 128, "dimensions": 3, "index": "i", "experiment_index": "e", "vectors": [[1.0]]}
    with pytest.raises(EmbeddingsDown, match="3 dimensions"):
        EmbeddingsClient(http(200, body), "/embeddings").question("a")


def test_a_question_with_a_model_sends_it() -> None:
    sent: list[bytes] = []

    def handle(request: httpx.Request) -> httpx.Response:
        sent.append(request.content)
        body = {"model": "m", "max_tokens": 9, "dimensions": 1, "index": "i", "experiment_index": "e", "vectors": [[1]]}
        return httpx.Response(200, json=body)

    client = httpx.Client(base_url="http://server", transport=httpx.MockTransport(handle))
    found = EmbeddingsClient(client, "/embeddings").question("a", "m", 9)
    assert found.vector == [1.0] and b'"model":"m"' in sent[0].replace(b" ", b"")


def test_an_experiment_that_is_not_there_is_none() -> None:
    assert EmbeddingsClient(http(404, {"detail": "no"}), "/embeddings").experiment("e1") is None


def test_a_search_without_index_finds_nothing_and_a_refused_one_is_rejected() -> None:
    assert DataClient(http(404, {"detail": "no index"}), "/data").search("vec_x", [1.0], 3) == []
    with pytest.raises(Rejected):
        DataClient(http(422, {"detail": "dimensions"}), "/data").search("vec_x", [1.0], 3)
    with pytest.raises(DataDown, match="data is not answering"):
        DataClient(http(503, {"detail": "Neo4j"}), "/data").search("vec_x", [1.0], 3)


def test_a_batch_carries_its_replace_from() -> None:
    key = NodeKey(GraphLabel.CHAT, "c1")
    assert batch_body(GraphBatch([GraphNode(key)], replace_from=key))["replace_from"] == {"label": "CHAT", "id": "c1"}
