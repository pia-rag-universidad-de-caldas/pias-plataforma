"""PiaaRepository over a GraphAdapter that records the queries: Cypher with enums and parameters, rows into models."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import LiteralString

import pytest

from data.models import (
    GraphAdapter,
    GraphError,
    GraphRow,
    GraphTransaction,
    Label,
    Node,
    NodeRef,
    Parameters,
    Relationship,
    RelationshipDefinition,
    RelationshipType,
)
from data.repository import PiaaRepository

ES = RelationshipDefinition(RelationshipType.ES, Label.PIAA, Label.JSON)
ROW: GraphRow = {
    "type": "ES",
    "source_label": "PIAA",
    "source_id": "p",
    "target_label": "JSON",
    "target_id": "j",
    "properties": {"desde": 1},
}
RELATIONSHIP = Relationship(RelationshipType.ES, NodeRef(Label.PIAA, "p"), NodeRef(Label.JSON, "j"), {"desde": 1})


class _NoTransaction(GraphTransaction):
    def run(self, cypher: LiteralString, parameters: Parameters | None = None) -> list[GraphRow]:
        raise AssertionError("no transaction outside a batch")


class Recording(GraphAdapter):
    def __init__(self, *answers: list[GraphRow]) -> None:
        self.answers = list(answers)
        self.reads: list[tuple[str, Parameters]] = []
        self.writes: list[tuple[str, Parameters]] = []

    def verify(self) -> None:
        pass

    def read(self, cypher: LiteralString, parameters: Parameters | None = None) -> list[GraphRow]:
        self.reads.append((cypher, parameters or {}))
        return self.answers.pop(0) if self.answers else []

    def write(self, cypher: LiteralString, parameters: Parameters | None = None) -> list[GraphRow]:
        self.writes.append((cypher, parameters or {}))
        return self.answers.pop(0) if self.answers else []

    @contextmanager
    def transaction(self) -> Iterator[GraphTransaction]:
        yield _NoTransaction()

    def close(self) -> None:
        pass


def test_there_is_one_constraint_per_label() -> None:
    graph = Recording()
    PiaaRepository(graph).ensure_constraints()
    assert len(graph.writes) == len(Label)
    assert "piaa_id_PIAA" in " ".join(c for c, _ in graph.writes)


def test_count_nodes_reads_the_total() -> None:
    assert PiaaRepository(Recording([{"total": 3}])).count_nodes(Label.PIAA) == 3


def test_a_count_that_isnt_a_number_is_a_graph_error() -> None:
    with pytest.raises(GraphError, match="expected an integer"):
        PiaaRepository(Recording([{"total": "x"}])).count_nodes(Label.PIAA)


def test_nodes_pass_the_page_as_parameters() -> None:
    graph = Recording([{"id": "a", "properties": {"id": "a", "x": 1}}])
    assert PiaaRepository(graph).nodes(Label.PIAA, 10, 5) == [Node(Label.PIAA, "a", {"x": 1})]
    assert graph.reads[0][1] == {"skip": 10, "limit": 5}


def test_nodes_can_leave_out_some_properties() -> None:
    graph = Recording([{"id": "r", "pairs": [["id", "r"], ["nombre", "plan.pdf"]]}])
    found = PiaaRepository(graph).nodes(Label.RAW, 0, 5, ["contenido"])
    assert found == [Node(Label.RAW, "r", {"nombre": "plan.pdf"})]
    cypher, parameters = graph.reads[0]
    assert "NOT (k IN $omit" in cypher and parameters["omit"] == ["contenido"]


def test_a_node_can_leave_out_some_properties() -> None:
    graph = Recording([{"id": "r", "pairs": [["tipo", "pdf"]]}])
    assert PiaaRepository(graph).node(Label.RAW, "r", ["contenido"]) == Node(Label.RAW, "r", {"tipo": "pdf"})


def test_a_node_doesnt_repeat_its_id_in_its_properties() -> None:
    node = PiaaRepository(Recording([{"id": "a", "properties": {"id": "a"}}])).node(Label.PIAA, "a")
    assert node == Node(Label.PIAA, "a", {})


def test_a_node_that_isnt_there_is_none() -> None:
    assert PiaaRepository(Recording()).node(Label.PIAA, "a") is None


def test_properties_that_arent_a_mapping_are_a_graph_error() -> None:
    with pytest.raises(GraphError, match="expected properties"):
        PiaaRepository(Recording([{"id": "a", "properties": 1}])).node(Label.PIAA, "a")


def test_create_node_sends_id_and_properties_as_parameters() -> None:
    graph = Recording([{"id": "a", "properties": {"x": 1}}])
    assert PiaaRepository(graph).create_node(Label.PIAA, "a", {"x": 1}) == Node(Label.PIAA, "a", {"x": 1})
    assert graph.writes[0][1] == {"id": "a", "properties": {"x": 1}}


@pytest.mark.parametrize(("replace", "assignment"), [(True, "n = $properties"), (False, "n += $properties")])
def test_update_node_replaces_or_merges(replace: bool, assignment: str) -> None:
    graph = Recording([{"id": "a", "properties": {}}])
    PiaaRepository(graph).update_node(Label.PIAA, "a", {}, replace)
    assert assignment in graph.writes[0][0]


def test_update_of_a_node_that_isnt_there_is_none() -> None:
    assert PiaaRepository(Recording()).update_node(Label.PIAA, "a", {}, True) is None


@pytest.mark.parametrize(("deleted", "expected"), [(1, True), (0, False)])
def test_delete_node_says_whether_it_existed(deleted: int, expected: bool) -> None:
    graph = Recording([{"deleted": deleted}])
    assert PiaaRepository(graph).delete_node(Label.PIAA, "a") is expected
    assert "DETACH DELETE" in graph.writes[0][0]


def test_node_relationships_are_read_as_models() -> None:
    assert PiaaRepository(Recording([ROW])).node_relationships(Label.PIAA, "p") == [RELATIONSHIP]


def test_count_relationships_reads_the_total() -> None:
    graph = Recording([{"total": 2}])
    assert PiaaRepository(graph).count_relationships(RelationshipType.ES) == 2
    assert "`ES`" in graph.reads[0][0]


def test_relationships_pass_the_page_as_parameters() -> None:
    graph = Recording([ROW])
    assert PiaaRepository(graph).relationships(RelationshipType.ES, 4, 2) == [RELATIONSHIP]
    assert (graph.reads[0][1]["skip"], graph.reads[0][1]["limit"]) == (4, 2)


def test_a_relationship_is_found_by_its_ends() -> None:
    graph = Recording([ROW])
    assert PiaaRepository(graph).relationship(ES, "p", "j") == RELATIONSHIP
    assert (graph.reads[0][1]["source"], graph.reads[0][1]["target"]) == ("p", "j")


def test_a_relationship_that_isnt_there_is_none() -> None:
    assert PiaaRepository(Recording()).relationship(ES, "p", "j") is None


def test_create_relationship_gives_what_it_created() -> None:
    assert PiaaRepository(Recording([ROW])).create_relationship(ES, "p", "j", {"desde": 1}) == RELATIONSHIP


def test_create_relationship_without_an_end_is_none() -> None:
    assert PiaaRepository(Recording()).create_relationship(ES, "p", "j", {}) is None


@pytest.mark.parametrize(("replace", "assignment"), [(True, "r = $properties"), (False, "r += $properties")])
def test_update_relationship_replaces_or_merges(replace: bool, assignment: str) -> None:
    graph = Recording([ROW])
    assert PiaaRepository(graph).update_relationship(ES, "p", "j", {}, replace) == RELATIONSHIP
    assert assignment in graph.writes[0][0]


def test_update_of_a_relationship_that_isnt_there_is_none() -> None:
    assert PiaaRepository(Recording()).update_relationship(ES, "p", "j", {}, True) is None


@pytest.mark.parametrize(("deleted", "expected"), [(1, True), (0, False)])
def test_delete_relationship_says_whether_it_existed(deleted: int, expected: bool) -> None:
    assert PiaaRepository(Recording([{"deleted": deleted}])).delete_relationship(ES, "p", "j") is expected
