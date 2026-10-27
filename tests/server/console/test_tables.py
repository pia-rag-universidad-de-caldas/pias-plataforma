"""Lists shown as tables and the actions a row leads to, with its data already in place (feature 035)."""

from collections.abc import Callable

from server.console.bodies import JsonValue
from server.console.catalog import Operation
from server.console.tables import row_actions, row_values, table

type Catalog = dict[str, tuple[Operation, ...]]
type Find = Callable[[str, str, str], Operation]

NODES: JsonValue = {
    "page": 2,
    "per_page": 50,
    "total": 120,
    "pages": 3,
    "nodes": [{"label": "PIAA", "id": "120501", "properties": {"nombre": "Cálculo I"}}],
}


def test_a_paginated_list_inside_the_answer() -> None:
    found = table(NODES)
    assert found is not None and found.key == "nodes" and (found.page, found.pages) == (2, 3)
    assert found.columns[:2] == ("id", "properties_nombre")
    assert found.rows[0]["label"] == "PIAA"


def test_a_plain_list_and_what_is_not_a_list() -> None:
    found = table([{"id": "e1", "name": "prueba", "status": "finished", "progress": {"done": 2}}])
    assert found is not None and found.columns[:3] == ("id", "name", "status") and found.pages is None
    assert found.rows[0]["progress_done"] == "2"
    assert table({"status": "ok"}) is None
    assert table({"a": [{"x": 1}], "b": [{"y": 2}]}) is None  # two lists: no single table


def test_a_node_row_leads_to_its_actions_with_label_and_id(operations: Catalog, find: Find) -> None:
    listing = find("data", "GET", "/nodes/{label}")
    actions = row_actions(listing, operations["data"])
    paths = {(op.method, op.path) for op in actions}
    assert ("DELETE", "/nodes/{label}/{id}") in paths and ("GET", "/nodes/{label}/{id}/relationships") in paths
    assert ("POST", "/nodes/{label}") not in paths  # needs nothing more than the list did
    found = table(NODES)
    assert found is not None
    read = find("data", "GET", "/nodes/{label}/{id}")
    assert row_values(found.rows[0], read, {"label": "PIAA"}) == {"label": "PIAA", "id": "120501"}


def test_a_score_row_keeps_the_experiment_and_gives_the_score(operations: Catalog, find: Find) -> None:
    patch = find("chunking", "PATCH", "/experiments/{id}/scores/{score_id}")
    values = row_values({"id": "s9", "author": "ana"}, patch, {"id": "exp1"})
    assert values == {"id": "exp1", "score_id": "s9"}


def test_an_ingesta_file_row_gives_its_origin(operations: Catalog, find: Find) -> None:
    listing = find("ingesta", "GET", "/data")
    content = find("ingesta", "GET", "/data/content")
    assert content in row_actions(listing, operations["ingesta"])
    assert row_values({"origen": "2024/x.pdf"}, content, {}) == {"origin": "2024/x.pdf"}
