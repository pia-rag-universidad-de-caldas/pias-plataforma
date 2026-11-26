"""Routes /progress over a graph that gives the rows each test scripts (features 042 and 043)."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from data.models import GraphRow

DataClient = Callable[..., TestClient]
COUNTS: GraphRow = {"total": 5, "done": 2, "partial": 1, "errors": 1, "never": 1}


@pytest.mark.parametrize("stage", ["parsing", "chunking"])
def test_the_counts_and_the_missing_ones(data_client: DataClient, stage: str) -> None:
    answer = data_client([COUNTS], [{"id": "c"}, {"id": "d"}]).get(f"/progress/{stage}?per_page=2")
    assert answer.status_code == 200
    body = answer.json()
    assert (body["total"], body["done"], body["missing"]) == (5, 2, 3)
    assert (body["listed"], body["pages"], body["sha256s"]) == ("missing", 2, ["c", "d"])


def test_list_done_pages_over_the_done_ones(data_client: DataClient) -> None:
    body = data_client([COUNTS], [{"id": "a"}]).get("/progress/parsing?list=done&per_page=1").json()
    assert (body["listed"], body["pages"], body["sha256s"]) == ("done", 2, ["a"])


def test_list_all_pages_over_every_one(data_client: DataClient) -> None:
    body = data_client([COUNTS], [{"id": "a"}, {"id": "c"}]).get("/progress/chunking?list=all&per_page=2").json()
    assert (body["listed"], body["pages"], body["sha256s"]) == ("all", 3, ["a", "c"])  # 5 in pages of 2


def test_an_unknown_list_is_422(data_client: DataClient) -> None:
    assert data_client().get("/progress/chunking?list=nope").status_code == 422


PROPERTY = "embedding_minilm_384"


def test_the_embeddings_progress_of_a_model(data_client: DataClient) -> None:
    body = data_client([COUNTS], [{"id": "c"}]).get(f"/progress/embeddings?property={PROPERTY}&per_page=1").json()
    assert (body["total"], body["missing"], body["sha256s"]) == (5, 3, ["c"])


@pytest.mark.parametrize("query", ["", "?property=huella`) DETACH DELETE j //"])
def test_the_embeddings_progress_needs_a_vector_property(data_client: DataClient, query: str) -> None:
    assert data_client().get(f"/progress/embeddings{query}").status_code == 422


def test_the_progress_of_an_embeddings_experiment(data_client: DataClient) -> None:
    answer = data_client([{"id": "x"}], [COUNTS], [{"id": "c"}]).get("/progress/experiment-embeddings?experiment=x")
    assert answer.status_code == 200 and answer.json()["sha256s"] == ["c"]


def test_the_progress_of_an_embeddings_experiment_that_isnt_there_is_404(data_client: DataClient) -> None:
    assert data_client([]).get("/progress/experiment-embeddings?experiment=x").status_code == 404
