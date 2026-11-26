"""Routes /relationships over a graph that gives the rows each test scripts: statuses, bodies and the schema."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from data.models import GraphRow

DataClient = Callable[..., TestClient]
NODE: GraphRow = {"id": "a", "properties": {}}
ROW: GraphRow = {
    "type": "ES",
    "source_label": "PIAA",
    "source_id": "p",
    "target_label": "JSON",
    "target_id": "j",
    "properties": {"x": 1},
}
BODY = {
    "type": "ES",
    "source": {"label": "PIAA", "id": "p"},
    "target": {"label": "JSON", "id": "j"},
    "properties": {"x": 1},
}
NEW = {"type": "ES", "source": {"label": "PIAA", "id": "p"}, "target": {"label": "JSON", "id": "j"}}
PATH = "/relationships/ES/PIAA/p/JSON/j"
OUT_OF_THE_SCHEMA = "/relationships/ES/JSON/j/PIAA/p"


def test_create_is_201(data_client: DataClient) -> None:
    answer = data_client([NODE], [NODE], [], [ROW]).post("/relationships", json=NEW)
    assert (answer.status_code, answer.json()) == (201, BODY)


def test_create_out_of_the_schema_is_422(data_client: DataClient) -> None:
    backwards = {"type": "ES", "source": NEW["target"], "target": NEW["source"]}
    assert data_client().post("/relationships", json=backwards).status_code == 422


@pytest.mark.parametrize("answers", [([],), ([NODE], [])])
def test_create_with_an_end_missing_is_404(data_client: DataClient, answers: tuple[list[GraphRow], ...]) -> None:
    assert data_client(*answers).post("/relationships", json=NEW).status_code == 404


def test_create_of_one_that_exists_is_409(data_client: DataClient) -> None:
    assert data_client([NODE], [NODE], [ROW]).post("/relationships", json=NEW).status_code == 409


def test_create_when_an_end_was_just_deleted_is_404(data_client: DataClient) -> None:
    assert data_client([NODE], [NODE], [], []).post("/relationships", json=NEW).status_code == 404


def test_a_page_of_relationships_with_its_counts(data_client: DataClient) -> None:
    answer = data_client([{"total": 1}], [ROW]).get("/relationships/ES")
    assert answer.json() == {"page": 1, "per_page": 50, "total": 1, "pages": 1, "relationships": [BODY]}


def test_read_a_relationship(data_client: DataClient) -> None:
    assert data_client([ROW]).get(PATH).json() == BODY


def test_read_one_that_isnt_there_is_404(data_client: DataClient) -> None:
    assert data_client([]).get(PATH).status_code == 404


def test_a_path_out_of_the_schema_is_422(data_client: DataClient) -> None:
    assert data_client().get(OUT_OF_THE_SCHEMA).status_code == 422


@pytest.mark.parametrize("method", ["PUT", "PATCH"])
def test_change_a_relationship(data_client: DataClient, method: str) -> None:
    answer = data_client([ROW]).request(method, PATH, json={"properties": {"x": 1}})
    assert (answer.status_code, answer.json()) == (200, BODY)


@pytest.mark.parametrize("method", ["PUT", "PATCH"])
def test_change_one_that_isnt_there_is_404(data_client: DataClient, method: str) -> None:
    assert data_client([]).request(method, PATH, json={"properties": {}}).status_code == 404


def test_delete_is_204(data_client: DataClient) -> None:
    assert data_client([{"deleted": 1}]).delete(PATH).status_code == 204


def test_delete_one_that_isnt_there_is_404(data_client: DataClient) -> None:
    assert data_client([{"deleted": 0}]).delete(PATH).status_code == 404
