"""PiaaRepository: CRUD of the PIAA graph's nodes and relationships on top of GraphAdapter (Cypher, no driver).

Neo4j doesn't accept labels or relationship types as parameters, so they are concatenated, but only values of the
closed enums Label and RelationshipType (never user text). Every other value always goes in parameters.
"""

from collections.abc import Mapping, Sequence
from typing import LiteralString, cast

from data.models import (
    BatchError,
    BatchNode,
    BatchResult,
    GraphAdapter,
    GraphError,
    GraphRow,
    GraphTransaction,
    GraphValue,
    Label,
    Node,
    NodeMode,
    NodeRef,
    Properties,
    PropertyValue,
    Relationship,
    RelationshipDefinition,
    RelationshipType,
)

_NODE: LiteralString = "n.id AS id, properties(n) AS properties"
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
# Relationships that mean "is part of": a batch's `replace_from` deletes what hangs from a node through them. The
# others are associations with nodes that other documents share (a NORMA, an ANTIPATRON, the FRAGMENTOS a CONSULTA
# was answered with...) and are never followed, so those nodes stay; nothing is followed upwards either.
# Experiments (025): from an EXPERIMENTO, EXP_GENERA → its sections → EXP_TIENE_CHUNK → their chunks, and
# EXP_TIENE_PUNTUACION → its scores; never EXP_USA
# (its EXP_DOCUMENTO are shared by other experiments) nor EXP_TIENE_SECCION (from a document it would reach the
# sections of every experiment).
# Pipeline (028): from a PIPE_CORRIDA, its iterations and events; never PIPE_USA (the experiments stay) nor PIPE_DE,
# and VIENE_DE (official JSON → its conversion) is never followed either.
_COMPOSITION: list[GraphValue] = [
    t.value
    for t in (
        RelationshipType.ES,
        RelationshipType.TIENE_SECCION,
        RelationshipType.TIENE_FRAGMENTO,
        RelationshipType.TIENE,
        RelationshipType.GENERA,
        RelationshipType.EXP_GENERA,
        RelationshipType.EXP_TIENE_CHUNK,
        RelationshipType.EXP_TIENE_PUNTUACION,
        RelationshipType.PIPE_TIENE_ITERACION,
        RelationshipType.PIPE_TIENE_EVENTO,
    )
]
_MAX_LISTED = 5  # missing relationship ends named in a BatchError


def _name(value: Label | RelationshipType) -> LiteralString:
    """Label or type ready for Cypher (between backticks). Only values of the closed enums."""
    text: LiteralString = value.value
    return "`" + text + "`"


def _assignment(variable: LiteralString, replace: bool) -> LiteralString:
    """`n = $p` removes the properties not sent; `n += $p` only changes the ones sent (null removes one)."""
    return variable + (" = $properties" if replace else " += $properties")


def _integer(value: GraphValue) -> int:
    if isinstance(value, int):
        return value
    raise GraphError(f"expected an integer and got {value!r}")


def _properties(value: GraphValue) -> Properties:
    """Neo4j only stores simple values and homogeneous lists, which already are PropertyValue. Without `id`."""
    if not isinstance(value, Mapping):
        raise GraphError(f"expected properties and got {value!r}")
    return {key: cast(PropertyValue, v) for key, v in value.items() if key != "id"}


def _node(label: Label, row: GraphRow) -> Node:
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
        """One uniqueness constraint on `id` per label (it also creates the index to look up by id)."""
        for label in Label:
            constraint: LiteralString = "`piaa_id_" + label.value + "`"
            self._graph.write(
                "CREATE CONSTRAINT " + constraint + " IF NOT EXISTS FOR (n:" + _name(label) + ") REQUIRE n.id IS UNIQUE"
            )

    # Nodes

    def count_nodes(self, label: Label) -> int:
        rows = self._graph.read("MATCH (n:" + _name(label) + ") RETURN count(n) AS total")
        return _integer(rows[0]["total"])

    def nodes(self, label: Label, skip: int, limit: int) -> list[Node]:
        rows = self._graph.read(
            "MATCH (n:" + _name(label) + ") RETURN " + _NODE + " ORDER BY id SKIP $skip LIMIT $limit",
            {"skip": skip, "limit": limit},
        )
        return [_node(label, row) for row in rows]

    def node(self, label: Label, id: str) -> Node | None:
        rows = self._graph.read("MATCH (n:" + _name(label) + " {id: $id}) RETURN " + _NODE, {"id": id})
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
        """Everything in one transaction, in this order: deletes the descendants of `replace_from` (not the node
        itself), merges the nodes by id (`replace`: properties = the ones sent; `ensure`: only if missing) and merges
        the relationships. One UNWIND statement per label and mode, and per relationship definition.

        The caller validates labels, types and the schema. Raises BatchError (and nothing is written) if a
        relationship end is neither in the batch nor in the graph (or `replace_from` just deleted it)."""
        with self._graph.transaction() as tx:
            deleted = self._delete_descendants(tx, replace_from) if replace_from else 0
            created = replaced = kept = merged = 0
            node_groups: dict[tuple[Label, NodeMode], list[BatchNode]] = {}
            for node in nodes:
                node_groups.setdefault((node.label, node.mode), []).append(node)
            for (label, mode), group in node_groups.items():
                new, total = self._merge_nodes(tx, label, mode, group)
                created += new
                if mode == NodeMode.REPLACE:
                    replaced += total - new
                elif mode == NodeMode.MERGE:
                    merged += total - new
                else:
                    kept += total - new
            relationship_groups: dict[RelationshipDefinition, list[Relationship]] = {}
            for relationship in relationships:
                key = RelationshipDefinition(relationship.type, relationship.source.label, relationship.target.label)
                relationship_groups.setdefault(key, []).append(relationship)
            written = sum(self._merge_relationships(tx, d, group) for d, group in relationship_groups.items())
        return BatchResult(deleted, created, replaced, kept, written, merged)

    @staticmethod
    def _delete_descendants(tx: GraphTransaction, root: NodeRef) -> int:
        rows = tx.run(
            "MATCH (root:" + _name(root.label) + " {id: $id})-[path*1..]->(d) "
            "WHERE all(r IN path WHERE type(r) IN $types) "
            "WITH DISTINCT d DETACH DELETE d RETURN count(*) AS deleted",
            {"id": root.id, "types": _COMPOSITION},
        )
        return _integer(rows[0]["deleted"])

    @staticmethod
    def _merge_nodes(tx: GraphTransaction, label: Label, mode: NodeMode, nodes: list[BatchNode]) -> tuple[int, int]:
        """(created, total) of a group of nodes with the same label and mode."""
        assignments: dict[NodeMode, LiteralString] = {
            NodeMode.REPLACE: "SET n = row.properties, n.id = row.id ",
            NodeMode.ENSURE: "ON CREATE SET n = row.properties, n.id = row.id ",
            NodeMode.MERGE: "SET n += row.properties ",
        }
        rows = tx.run(
            "UNWIND $rows AS row OPTIONAL MATCH (old:"
            + _name(label)
            + " {id: row.id}) WITH row, old IS NULL AS new MERGE (n:"
            + _name(label)
            + " {id: row.id}) "
            + assignments[mode]
            + "RETURN count(*) AS total, sum(CASE WHEN new THEN 1 ELSE 0 END) AS created",
            {"rows": [{"id": n.id, "properties": n.properties} for n in nodes]},
        )
        return _integer(rows[0]["created"]), _integer(rows[0]["total"])

    @staticmethod
    def _merge_relationships(
        tx: GraphTransaction, definition: RelationshipDefinition, relationships: list[Relationship]
    ) -> int:
        """Merges a group of relationships with the same definition; BatchError if any end is missing."""
        rows = tx.run(
            "UNWIND $rows AS row MATCH (a:"
            + _name(definition.source)
            + " {id: row.source}) MATCH (b:"
            + _name(definition.target)
            + " {id: row.target}) MERGE (a)-[r:"
            + _name(definition.type)
            + "]->(b) SET r = row.properties RETURN row.source AS source, row.target AS target",
            {
                "rows": [
                    {"source": r.source.id, "target": r.target.id, "properties": r.properties} for r in relationships
                ]
            },
        )
        merged = {(str(row["source"]), str(row["target"])) for row in rows}
        missing = [r for r in relationships if (r.source.id, r.target.id) not in merged]
        if missing:
            listed = ", ".join(
                f"({definition.source} {r.source.id!r})-[:{definition.type}]->({definition.target} {r.target.id!r})"
                for r in missing[:_MAX_LISTED]
            )
            more = f" and {len(missing) - _MAX_LISTED} more" if len(missing) > _MAX_LISTED else ""
            raise BatchError(f"{len(missing)} relationships have an end that doesn't exist: {listed}{more}")
        return len(relationships)
