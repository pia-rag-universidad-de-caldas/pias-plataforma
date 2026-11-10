"""GraphBatchWriter (feature 022): many nodes and relationships in one transaction, all or nothing."""

from collections import Counter
from collections.abc import Sequence
from typing import ClassVar, LiteralString

from data.models import (
    BatchError,
    BatchNode,
    BatchResult,
    GraphAdapter,
    GraphTransaction,
    GraphValue,
    Label,
    NodeMode,
    NodeRef,
    Relationship,
    RelationshipDefinition,
)
from data.schema import COMPOSITION

from .cypher import integer, name

_COMPOSITION: list[GraphValue] = [t.value for t in COMPOSITION]
_MAX_LISTED = 5  # missing relationship ends named in a BatchError


class GraphBatchWriter:
    # What each mode does to the node's properties, and the BatchResult counter of the nodes that already existed.
    _ASSIGNMENTS: ClassVar[dict[NodeMode, LiteralString]] = {
        NodeMode.REPLACE: "SET n = row.properties, n.id = row.id ",
        NodeMode.ENSURE: "ON CREATE SET n = row.properties, n.id = row.id ",
        NodeMode.MERGE: "SET n += row.properties ",
    }
    _EXISTING: ClassVar[dict[NodeMode, str]] = {
        NodeMode.REPLACE: "replaced",
        NodeMode.ENSURE: "kept",
        NodeMode.MERGE: "merged",
    }

    def __init__(self, graph: GraphAdapter) -> None:
        self._graph = graph

    def write(
        self, nodes: Sequence[BatchNode], relationships: Sequence[Relationship], replace_from: NodeRef | None
    ) -> BatchResult:
        """Everything in one transaction, in this order: deletes the descendants of `replace_from` (not the node
        itself), merges the nodes by id (`replace`: properties = the ones sent; `ensure`: only if missing; `merge`:
        the ones sent over the others) and merges the relationships. One UNWIND statement per label and mode, and
        per relationship definition.

        The caller validates labels, types and the schema (data.schema.batch_problems). Raises BatchError (and nothing
        is written) if a relationship end is neither in the batch nor in the graph (or `replace_from` just deleted
        it)."""
        with self._graph.transaction() as tx:
            deleted = self._delete_descendants(tx, replace_from) if replace_from else 0
            created = 0
            existing: Counter[str] = Counter()
            node_groups: dict[tuple[Label, NodeMode], list[BatchNode]] = {}
            for node in nodes:
                node_groups.setdefault((node.label, node.mode), []).append(node)
            for (label, mode), group in node_groups.items():
                new, total = self._merge_nodes(tx, label, mode, group)
                created += new
                existing[self._EXISTING[mode]] += total - new
            relationship_groups: dict[RelationshipDefinition, list[Relationship]] = {}
            for relationship in relationships:
                key = RelationshipDefinition(relationship.type, relationship.source.label, relationship.target.label)
                relationship_groups.setdefault(key, []).append(relationship)
            written = sum(self._merge_relationships(tx, d, group) for d, group in relationship_groups.items())
        return BatchResult(deleted, created, existing["replaced"], existing["kept"], written, existing["merged"])

    @staticmethod
    def _delete_descendants(tx: GraphTransaction, root: NodeRef) -> int:
        rows = tx.run(
            "MATCH (root:" + name(root.label) + " {id: $id})-[path*1..]->(d) "
            "WHERE all(r IN path WHERE type(r) IN $types) "
            "WITH DISTINCT d DETACH DELETE d RETURN count(*) AS deleted",
            {"id": root.id, "types": _COMPOSITION},
        )
        return integer(rows[0]["deleted"])

    @staticmethod
    def _merge_nodes(tx: GraphTransaction, label: Label, mode: NodeMode, nodes: list[BatchNode]) -> tuple[int, int]:
        """(created, total) of a group of nodes with the same label and mode."""
        rows = tx.run(
            "UNWIND $rows AS row OPTIONAL MATCH (old:"
            + name(label)
            + " {id: row.id}) WITH row, old IS NULL AS new MERGE (n:"
            + name(label)
            + " {id: row.id}) "
            + GraphBatchWriter._ASSIGNMENTS[mode]
            + "RETURN count(*) AS total, sum(CASE WHEN new THEN 1 ELSE 0 END) AS created",
            {"rows": [{"id": n.id, "properties": n.properties} for n in nodes]},
        )
        return integer(rows[0]["created"]), integer(rows[0]["total"])

    @staticmethod
    def _merge_relationships(
        tx: GraphTransaction, definition: RelationshipDefinition, relationships: list[Relationship]
    ) -> int:
        """Merges a group of relationships with the same definition; BatchError if any end is missing."""
        rows = tx.run(
            "UNWIND $rows AS row MATCH (a:"
            + name(definition.source)
            + " {id: row.source}) MATCH (b:"
            + name(definition.target)
            + " {id: row.target}) MERGE (a)-[r:"
            + name(definition.type)
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
