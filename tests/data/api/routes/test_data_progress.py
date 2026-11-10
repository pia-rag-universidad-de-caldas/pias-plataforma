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


def test_an_unknown_list_is_422(data_client: DataClient) -> None:
    assert data_client().get("/progress/chunking?list=nope").status_code == 422
