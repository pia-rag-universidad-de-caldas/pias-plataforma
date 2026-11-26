"""PiaaRepository: CRUD of the PIAA graph's nodes and relationships on top of GraphAdapter (Cypher, no driver).

Neo4j doesn't accept labels or relationship types as parameters, so they are concatenated, but only values of the
closed enums Label and RelationshipType (never user text, see cypher.name). Every other value always goes in
parameters. The batches are GraphBatchWriter's.
"""

from collections.abc import Mapping, Sequence
from typing import LiteralString, cast

from data.models import (
    BatchNode,
    BatchResult,
    GraphAdapter,
    GraphError,
    GraphRow,
    GraphValue,
    Label,
    Node,
    NodeRef,
    Parameters,
    Properties,
    PropertyValue,
    Relationship,
    RelationshipDefinition,
    RelationshipType,
)

from .batch_writer import GraphBatchWriter
from .cypher import integer as _integer
from .cypher import name as _name
from .document_repository import DocumentRepository

_NODE: LiteralString = "n.id AS id, properties(n) AS properties"
# Without some properties (feature 042: a RAW without its `contenido`): what is left of the node, as [key, value] pairs.
# `embedding` names every vector property (feature 055: `embedding_<model>_<dim>`, one per model): ?omit=embedding
# leaves them all out, as it did when there was only one.
_NODE_WITHOUT: LiteralString = (
    "n.id AS id, [k IN keys(n) WHERE NOT (k IN $omit OR ('embedding' IN $omit AND k =~ 'embedding_[a-z0-9_]+'))"
    " | [k, n[k]]] AS pairs"
)
# For each end, its first known label (in case someone added others outside the API).
_RELATIONSHIP: LiteralString = (
    "type(r) AS type, "
    "[l IN labels(a) WHERE l IN $labels][0] AS source_label, a.id AS source_id, "
    "[l IN labels(b) WHERE l IN $labels][0] AS target_label, b.id AS target_id, "
    "properties(r) AS properties"
)
_RELATIONSHIP_ORDER: LiteralString = " ORDER BY type, source_label, source_id, target_label, target_id"
_LABELS: list[GraphValue] = [label.value for label in Label]
_TYPES: list[GraphValue] = [type.value for type in RelationshipType]


def _assignment(variable: LiteralString, replace: bool) -> LiteralString:
    """`n = $p` removes the properties not sent; `n += $p` only changes the ones sent (null removes one)."""
    return variable + (" = $properties" if replace else " += $properties")


def _properties(value: GraphValue) -> Properties:
    """Neo4j only stores simple values and homogeneous lists, which already are PropertyValue. Without `id`."""
    if not isinstance(value, Mapping):
        raise GraphError(f"expected properties and got {value!r}")
    return {key: cast(PropertyValue, v) for key, v in value.items() if key != "id"}


def _node(label: Label, row: GraphRow) -> Node:
    if "pairs" in row:
        pairs = row["pairs"]
        if not isinstance(pairs, list):
            raise GraphError(f"expected [key, value] pairs and got {pairs!r}")
        found = {str(pair[0]): pair[1] for pair in pairs if isinstance(pair, list) and len(pair) == 2}
        return Node(label, str(row["id"]), _properties(found))
    return Node(label, str(row["id"]), _properties(row["properties"]))


def _relationship(row: GraphRow) -> Relationship:
    return Relationship(
        RelationshipType(str(row["type"])),
        NodeRef(Label(str(row["source_label"])), str(row["source_id"])),
        NodeRef(Label(str(row["target_label"])), str(row["target_id"])),
        _properties(row["properties"]),
    )


def _pattern(definition: RelationshipDefinition) -> LiteralString:
    """MATCH of the `definition` relationship between the nodes with id $source and $target."""
    return (
        "MATCH (a:"
        + _name(definition.source)
        + " {id: $source})-[r:"
        + _name(definition.type)
        + "]->(b:"
        + _name(definition.target)
        + " {id: $target})"
    )


class PiaaRepository:
    def __init__(self, graph: GraphAdapter) -> None:
        self._graph = graph

    def ensure_constraints(self) -> None:
        """One uniqueness constraint on `id` per label (it also creates the index to look up by id), and the full-text
        index of the documents by their course."""
        for label in Label:
            constraint: LiteralString = "`piaa_id_" + label.value + "`"
            self._graph.write(
                "CREATE CONSTRAINT " + constraint + " IF NOT EXISTS FOR (n:" + _name(label) + ") REQUIRE n.id IS UNIQUE"
            )
        self._graph.write(
            "CREATE INDEX piaa_pipeline_run_status_actor IF NOT EXISTS FOR (n:PIPE_CORRIDA) ON (n.estado, n.actor)"
        )
        DocumentRepository(self._graph).ensure_index()  # the documents by their course (feature 057)

    # Nodes

    def count_nodes(self, label: Label) -> int:
        rows = self._graph.read("MATCH (n:" + _name(label) + ") RETURN count(n) AS total")
        return _integer(rows[0]["total"])

    def nodes(self, label: Label, skip: int, limit: int, omit: Sequence[str] = ()) -> list[Node]:
        """`omit`: properties left out of the answer (a big one, like a RAW's `contenido`)."""
        rows = self._graph.read(
            "MATCH (n:"
            + _name(label)
            + ") RETURN "
            + (_NODE_WITHOUT if omit else _NODE)
            + " ORDER BY id SKIP $skip LIMIT $limit",
            {"skip": skip, "limit": limit} | ({"omit": list(omit)} if omit else {}),
        )
        return [_node(label, row) for row in rows]

    def count_pipeline_runs(self, status: str, actor: str | None = None) -> int:
        """Count pipeline runs by indexed status, optionally for one actor (the review inbox)."""
        where = "n.estado = $status" + (" AND n.actor = $actor" if actor is not None else "")
        parameters: Parameters = {"status": status} | ({"actor": actor} if actor is not None else {})
        rows = self._graph.read("MATCH (n:PIPE_CORRIDA) WHERE " + where + " RETURN count(n) AS total", parameters)
        return _integer(rows[0]["total"])

    def pipeline_runs(self, status: str, actor: str | None, skip: int, limit: int) -> list[Node]:
        """Read one page of pipeline runs by indexed status, optionally for one actor."""
        where = "n.estado = $status" + (" AND n.actor = $actor" if actor is not None else "")
        parameters: dict[str, GraphValue] = {"status": status, "skip": skip, "limit": limit}
        if actor is not None:
            parameters["actor"] = actor
        rows = self._graph.read(
            "MATCH (n:PIPE_CORRIDA) WHERE "
            + where
            + " RETURN "
            + _NODE
            + " ORDER BY n.creado_en, n.id SKIP $skip LIMIT $limit",
            parameters,
        )
        return [_node(Label.PIPE_CORRIDA, row) for row in rows]

    def node(self, label: Label, id: str, omit: Sequence[str] = ()) -> Node | None:
        rows = self._graph.read(
            "MATCH (n:" + _name(label) + " {id: $id}) RETURN " + (_NODE_WITHOUT if omit else _NODE),
            {"id": id} | ({"omit": list(omit)} if omit else {}),
        )
        return _node(label, rows[0]) if rows else None

    def create_node(self, label: Label, id: str, properties: Properties) -> Node:
        """Doesn't check whether the id exists (the caller does); if it does, the constraint rejects it (GraphError)."""
        rows = self._graph.write(
            "CREATE (n:" + _name(label) + ") SET n = $properties, n.id = $id RETURN " + _NODE,
            {"id": id, "properties": properties},
        )
        return _node(label, rows[0])

    def update_node(self, label: Label, id: str, properties: Properties, replace: bool) -> Node | None:
        """Changes the properties (all of them or only the ones sent); the id stays. None if the node doesn't exist."""
        rows = self._graph.write(
            "MATCH (n:"
            + _name(label)
            + " {id: $id}) SET "
            + _assignment("n", replace)
            + ", n.id = $id RETURN "
            + _NODE,
            {"id": id, "properties": properties},
        )
        return _node(label, rows[0]) if rows else None

    def delete_node(self, label: Label, id: str) -> bool:
        """Deletes the node and its relationships. False if it didn't exist."""
        rows = self._graph.write(
            "MATCH (n:" + _name(label) + " {id: $id}) DETACH DELETE n RETURN count(*) AS deleted", {"id": id}
        )
        return _integer(rows[0]["deleted"]) > 0

    def node_relationships(self, label: Label, id: str) -> list[Relationship]:
        """The schema relationships coming into or out of the node."""
        rows = self._graph.read(
            "MATCH (n:" + _name(label) + " {id: $id})-[r]-() WHERE type(r) IN $types "
            "WITH DISTINCT r WITH r, startNode(r) AS a, endNode(r) AS b RETURN " + _RELATIONSHIP + _RELATIONSHIP_ORDER,
            {"id": id, "types": _TYPES, "labels": _LABELS},
        )
        return [_relationship(row) for row in rows]

    # Relationships

    def count_relationships(self, type: RelationshipType) -> int:
        rows = self._graph.read("MATCH ()-[r:" + _name(type) + "]->() RETURN count(r) AS total")
        return _integer(rows[0]["total"])

    def relationships(self, type: RelationshipType, skip: int, limit: int) -> list[Relationship]:
        rows = self._graph.read(
            "MATCH (a)-[r:"
            + _name(type)
            + "]->(b) RETURN "
            + _RELATIONSHIP
            + _RELATIONSHIP_ORDER
            + " SKIP $skip LIMIT $limit",
            {"skip": skip, "limit": limit, "labels": _LABELS},
        )
        return [_relationship(row) for row in rows]

    def relationship(self, definition: RelationshipDefinition, source: str, target: str) -> Relationship | None:
        rows = self._graph.read(
            _pattern(definition) + " RETURN " + _RELATIONSHIP + " LIMIT 1",
            {"source": source, "target": target, "labels": _LABELS},
        )
        return _relationship(rows[0]) if rows else None

    def create_relationship(
        self, definition: RelationshipDefinition, source: str, target: str, properties: Properties
    ) -> Relationship | None:
        """Doesn't check whether it exists (the caller does). None if either node is missing."""
        rows = self._graph.write(
            "MATCH (a:"
            + _name(definition.source)
            + " {id: $source}), (b:"
            + _name(definition.target)
            + " {id: $target}) CREATE (a)-[r:"
            + _name(definition.type)
            + "]->(b) SET r = $properties "
            "RETURN " + _RELATIONSHIP,
            {"source": source, "target": target, "properties": properties, "labels": _LABELS},
        )
        return _relationship(rows[0]) if rows else None

    def update_relationship(
        self, definition: RelationshipDefinition, source: str, target: str, properties: Properties, replace: bool
    ) -> Relationship | None:
        rows = self._graph.write(
            _pattern(definition) + " SET " + _assignment("r", replace) + " RETURN " + _RELATIONSHIP,
            {"source": source, "target": target, "properties": properties, "labels": _LABELS},
        )
        return _relationship(rows[0]) if rows else None

    def delete_relationship(self, definition: RelationshipDefinition, source: str, target: str) -> bool:
        rows = self._graph.write(
            _pattern(definition) + " DELETE r RETURN count(*) AS deleted", {"source": source, "target": target}
        )
        return _integer(rows[0]["deleted"]) > 0

    # Batch (feature 022)

    def write_batch(
        self, nodes: Sequence[BatchNode], relationships: Sequence[Relationship], replace_from: NodeRef | None
    ) -> BatchResult:
        """Everything in one transaction (see GraphBatchWriter)."""
        return GraphBatchWriter(self._graph).write(nodes, relationships, replace_from)
