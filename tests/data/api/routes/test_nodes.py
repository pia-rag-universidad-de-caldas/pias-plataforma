"""Routes /nodes over a graph that gives the rows each test scripts: statuses and bodies."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from data.models import GraphRow

DataClient = Callable[..., TestClient]
NODE: GraphRow = {"id": "a", "properties": {"x": 1}}
BODY = {"label": "PIAA", "id": "a", "properties": {"x": 1}}
RELATION: GraphRow = {
    "type": "ES",
    "source_label": "PIAA",
    "source_id": "a",
    "target_label": "JSON",
    "target_id": "j",
    "properties": {},
}


def test_a_page_of_nodes_with_its_counts(data_client: DataClient) -> None:
    answer = data_client([{"total": 3}], [NODE]).get("/nodes/PIAA?page=1&per_page=2")
    assert answer.status_code == 200
    assert answer.json() == {"page": 1, "per_page": 2, "total": 3, "pages": 2, "nodes": [BODY]}


@pytest.mark.parametrize("query", ["page=0", "per_page=0", "per_page=501"])
def test_a_page_out_of_its_limits_is_422(data_client: DataClient, query: str) -> None:
    assert data_client().get(f"/nodes/PIAA?{query}").status_code == 422


def test_a_label_out_of_the_schema_is_422(data_client: DataClient) -> None:
    assert data_client().get("/nodes/NADA").status_code == 422


def test_create_with_an_id_is_201(data_client: DataClient) -> None:
    answer = data_client([], [NODE]).post("/nodes/PIAA", json={"id": "a", "properties": {"x": 1}})
    assert (answer.status_code, answer.json()) == (201, BODY)


def test_create_without_an_id_generates_one(data_client: DataClient) -> None:
    answer = data_client([], [{"id": "generated", "properties": {}}]).post("/nodes/PIAA", json={})
    assert answer.status_code == 201


def test_create_of_an_id_that_exists_is_409(data_client: DataClient) -> None:
    assert data_client([NODE]).post("/nodes/PIAA", json={"id": "a"}).status_code == 409


def test_read_a_node(data_client: DataClient) -> None:
    assert data_client([NODE]).get("/nodes/PIAA/a").json() == BODY


def test_read_a_node_that_isnt_there_is_404(data_client: DataClient) -> None:
    assert data_client([]).get("/nodes/PIAA/a").status_code == 404


@pytest.mark.parametrize("method", ["PUT", "PATCH"])
def test_change_a_node(data_client: DataClient, method: str) -> None:
    answer = data_client([NODE]).request(method, "/nodes/PIAA/a", json={"properties": {"x": 1}})
    assert (answer.status_code, answer.json()) == (200, BODY)


@pytest.mark.parametrize("method", ["PUT", "PATCH"])
def test_change_a_node_that_isnt_there_is_404(data_client: DataClient, method: str) -> None:
    assert data_client([]).request(method, "/nodes/PIAA/a", json={"properties": {}}).status_code == 404


def test_delete_a_node_is_204(data_client: DataClient) -> None:
    assert data_client([{"deleted": 1}]).delete("/nodes/PIAA/a").status_code == 204


def test_delete_a_node_that_isnt_there_is_404(data_client: DataClient) -> None:
    assert data_client([{"deleted": 0}]).delete("/nodes/PIAA/a").status_code == 404


def test_the_relationships_of_a_node(data_client: DataClient) -> None:
    answer = data_client([NODE], [RELATION]).get("/nodes/PIAA/a/relationships")
    assert [r["type"] for r in answer.json()] == ["ES"]


def test_the_relationships_of_a_node_that_isnt_there_are_404(data_client: DataClient) -> None:
    assert data_client([]).get("/nodes/PIAA/a/relationships").status_code == 404
