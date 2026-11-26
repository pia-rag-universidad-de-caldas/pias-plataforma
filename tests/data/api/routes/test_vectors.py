"""Routes /vectors over a graph that gives the rows each test scripts (feature 046)."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from data.models import GraphRow

DataClient = Callable[..., TestClient]
INDEX: GraphRow = {"name": "vec_x", "label": "FRAGMENTOS", "property": "embedding_x_3", "dimensions": 3}
HIT: GraphRow = {
    "id": "a:0",
    "score": 0.5,
    "text": "uno",
    "headings": ["t"],
    "pages": [1],
    "sha256": "a",
    "origin": "o",
    "code": None,
    "activity": "Cálculo",
}


def test_an_invalid_name_or_label_is_422_without_touching_the_graph(data_client: DataClient) -> None:
    client = data_client()  # any query would fail: the script is empty
    assert (
        client.put(
            "/vectors/indexes/bad", json={"label": "FRAGMENTOS", "property": "embedding_x_3", "dimensions": 3}
        ).status_code
        == 422
    )
    assert (
        client.put(
            "/vectors/indexes/vec_x", json={"label": "JSON", "property": "embedding_x_3", "dimensions": 3}
        ).status_code
        == 422
    )
    assert (
        client.put(
            "/vectors/indexes/vec_x", json={"label": "NOPE", "property": "embedding_x_3", "dimensions": 3}
        ).status_code
        == 422
    )
    bad = {"label": "FRAGMENTOS", "property": "embedding; DROP", "dimensions": 3}
    assert client.put("/vectors/indexes/vec_x", json=bad).status_code == 422


def test_a_missing_index_is_created_and_answered(data_client: DataClient) -> None:
    answer = data_client([], [], [], [INDEX]).put(
        "/vectors/indexes/vec_x", json={"label": "FRAGMENTOS", "property": "embedding_x_3", "dimensions": 3}
    )
    assert answer.status_code == 200 and answer.json()["dimensions"] == 3


def test_an_index_with_another_definition_is_409(data_client: DataClient) -> None:
    answer = data_client([INDEX]).put(
        "/vectors/indexes/vec_x", json={"label": "FRAGMENTOS", "property": "embedding_x_3", "dimensions": 384}
    )
    assert answer.status_code == 409


def test_another_index_on_the_same_label_is_409(data_client: DataClient) -> None:
    answer = data_client([], [INDEX]).put(
        "/vectors/indexes/vec_y", json={"label": "FRAGMENTOS", "property": "embedding_x_3", "dimensions": 3}
    )
    assert answer.status_code == 409 and "vec_x" in answer.json()["detail"]


def test_dropping_an_index_that_does_not_exist_is_404(data_client: DataClient) -> None:
    assert data_client([]).delete("/vectors/indexes/vec_x").status_code == 404


def test_dropping_an_index_with_its_property_removes_it_from_the_nodes(data_client: DataClient) -> None:
    client = data_client([INDEX], [], [{"removed": 2}])  # find, DROP INDEX, REMOVE (fewer than a batch: done)
    assert client.delete("/vectors/indexes/vec_x?drop_property=true").status_code == 204


def test_a_search_in_an_index_that_does_not_exist_is_404(data_client: DataClient) -> None:
    assert data_client([]).post("/vectors/search", json={"index": "vec_x", "vector": [1.0]}).status_code == 404


def test_a_vector_of_other_dimensions_is_422(data_client: DataClient) -> None:
    assert data_client([INDEX]).post("/vectors/search", json={"index": "vec_x", "vector": [1.0]}).status_code == 422


def test_a_search_answers_the_chunks(data_client: DataClient) -> None:
    answer = data_client([INDEX], [HIT]).post("/vectors/search", json={"index": "vec_x", "vector": [1.0, 0.0, 0.0]})
    assert answer.status_code == 200
    assert answer.json() == [HIT]


EXP_INDEX: GraphRow = {**INDEX, "label": "EXP_EMBED"}
EXPERIMENT_SEARCH = {"index": "vec_x", "vector": [1.0, 0.0, 0.0], "experiment": "e1"}


def test_a_search_of_an_experiment_needs_an_exp_chunk_index(data_client: DataClient) -> None:
    assert data_client([INDEX]).post("/vectors/search", json=EXPERIMENT_SEARCH).status_code == 422


def test_a_search_without_experiment_in_an_exp_chunk_index_is_422(data_client: DataClient) -> None:
    body = {"index": "vec_x", "vector": [1.0, 0.0, 0.0]}
    assert data_client([EXP_INDEX]).post("/vectors/search", json=body).status_code == 422


def test_a_search_of_an_experiment_answers_its_chunks(data_client: DataClient) -> None:
    answer = data_client([EXP_INDEX], [HIT]).post("/vectors/search", json=EXPERIMENT_SEARCH)
    assert answer.status_code == 200 and answer.json() == [HIT]


def test_a_search_over_some_documents_reads_only_their_chunks(data_client: DataClient) -> None:
    body = {"index": "vec_x", "vector": [1.0, 0.0, 0.0], "sha256s": ["a"]}
    answer = data_client([INDEX], [HIT]).post("/vectors/search", json=body)
    assert answer.status_code == 200 and answer.json() == [HIT]


@pytest.mark.parametrize("extra", [{"sha256s": []}, {"sha256s": ["a"], "experiment": "e1"}])
def test_a_search_over_documents_out_of_its_rules_is_422(data_client: DataClient, extra: dict[str, object]) -> None:
    body = {"index": "vec_x", "vector": [1.0, 0.0, 0.0], **extra}
    assert data_client([INDEX]).post("/vectors/search", json=body).status_code == 422
