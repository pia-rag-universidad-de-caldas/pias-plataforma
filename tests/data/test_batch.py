"""POST /batch (feature 022): checked before touching the graph, written in one transaction, and `replace_from` only
follows composition relationships. Against a recording GraphAdapter: no Neo4j."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import LiteralString

from fastapi.testclient import TestClient

from data.api import ApiSettings, create_app
from data.models import (
    BatchNode,
    GraphAdapter,
    GraphRow,
    GraphTransaction,
    Label,
    NodeRef,
    Parameters,
    Relationship,
    RelationshipType,
)
from data.schema import COMPOSITION, RELATIONSHIPS, batch_problems


class Recording(GraphTransaction):
    def __init__(self, statements: list[tuple[str, Parameters]]) -> None:
        self.statements = statements

    def run(self, cypher: LiteralString, parameters: Parameters | None = None) -> list[GraphRow]:
        parameters = parameters or {}
        self.statements.append((cypher, parameters))
        rows = parameters.get("rows")
        if "DETACH DELETE" in cypher:
            return [{"deleted": 4}]
        if "OPTIONAL MATCH (old" in cypher and isinstance(rows, list):
            return [{"created": 1, "total": len(rows)}]  # one new per group, the rest already there
        if isinstance(rows, list):  # relationships: every end found
            return [{"source": r["source"], "target": r["target"]} for r in rows if isinstance(r, dict)]
        return []


class Graph(GraphAdapter):
    def __init__(self) -> None:
        self.statements: list[tuple[str, Parameters]] = []

    def verify(self) -> None:
        pass

    def read(self, cypher: LiteralString, parameters: Parameters | None = None) -> list[GraphRow]:
        raise AssertionError("a batch never reads outside its transaction")

    def write(self, cypher: LiteralString, parameters: Parameters | None = None) -> list[GraphRow]:
        raise AssertionError("a batch writes in one transaction")

    @contextmanager
    def transaction(self) -> Iterator[GraphTransaction]:
        yield Recording(self.statements)

    def close(self) -> None:
        pass


def post(graph: Graph, body: object) -> tuple[int, object]:
    client = TestClient(create_app(ApiSettings("neo4j://x", "neo4j", None), graph))
    answer = client.post("/batch", json=body)
    return answer.status_code, answer.json()


def node(label: str, id: str, mode: str = "replace") -> dict[str, object]:
    return {"label": label, "id": id, "properties": {}, "mode": mode}


def link(type: str, source: tuple[str, str], target: tuple[str, str]) -> dict[str, object]:
    return {
        "type": type,
        "source": {"label": source[0], "id": source[1]},
        "target": {"label": target[0], "id": target[1]},
    }


def test_a_bad_batch_is_422_listing_every_problem_and_writes_nothing() -> None:
    graph = Graph()
    status, body = post(
        graph,
        {
            "nodes": [node("JSON", ""), node("JSON", "d"), node("JSON", "d")],
            "relationships": [
                link("ES", ("JSON", "d"), ("PIAA", "p")),  # the schema only has PIAA -ES-> JSON
                link("TIENE_SECCION", ("JSON", "d"), ("SECCION", "s")),
                link("TIENE_SECCION", ("JSON", "d"), ("SECCION", "s")),
            ],
        },
    )
    assert status == 422 and graph.statements == []
    detail = str(body)
    assert "empty id in a JSON node" in detail
    assert "the JSON node 'd' comes 2 times" in detail
    assert "doesn't allow (JSON)-[:ES]->(PIAA)" in detail
    assert "comes 2 times" in detail.split("doesn't allow")[1]


def test_a_batch_counts_by_mode_and_replaces_only_through_composition() -> None:
    graph = Graph()
    status, body = post(
        graph,
        {
            "nodes": [
                node("PIAA", "p", "ensure"),
                node("PIAA", "q", "ensure"),
                node("JSON", "d", "replace"),
                node("JSON", "e", "replace"),
                node("EXPERIMENTO", "x", "merge"),
            ],
            "relationships": [link("ES", ("PIAA", "p"), ("JSON", "d"))],
            "replace_from": {"label": "JSON", "id": "d"},
        },
    )
    assert status == 200
    assert body == {"deleted": 4, "created": 3, "replaced": 1, "kept": 1, "relationships": 1, "merged": 0}
    cypher, parameters = graph.statements[0]
    assert "DETACH DELETE" in cypher and parameters["id"] == "d"
    followed = parameters["types"]
    assert isinstance(followed, list)
    assert {"ES", "TIENE_SECCION", "TIENE_FRAGMENTO", "EXP_GENERA", "EXP_TIENE_CHUNK", "PIPE_TIENE_EVENTO"} <= set(
        followed
    )
    # Shared nodes are never deleted: conversions used by other experiments, the experiments a pipeline used, the
    # pipeline template and the conversion an official JSON came from.
    assert not {"EXP_USA", "EXP_TIENE_SECCION", "PIPE_USA", "PIPE_DE", "VIENE_DE", "SOBRE", "EN"} & set(followed)


def test_every_composition_relationship_is_in_the_schema_and_shared_ones_are_not_composition() -> None:
    assert {d.type for d in RELATIONSHIPS} >= COMPOSITION
    shared = {RelationshipType.EXP_USA, RelationshipType.EXP_TIENE_SECCION, RelationshipType.PIPE_USA}
    assert not shared & COMPOSITION


def test_batch_problems_is_empty_for_a_good_batch() -> None:
    piaa, json = NodeRef(Label.PIAA, "p"), NodeRef(Label.JSON, "d")
    nodes = [BatchNode(Label.PIAA, "p", {}), BatchNode(Label.JSON, "d", {})]
    assert batch_problems(nodes, [Relationship(RelationshipType.ES, piaa, json, {})]) == []
