"""What parsing writes in the graph, as one batch (POST /data/batch). Labels and relationship types are data's (it
owns the schema); their VALUES and the property names are stored in Neo4j: they stay in Spanish."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

type Properties = Mapping[str, object]  # in practice one of the TypedDicts of stored.py


class GraphLabel(StrEnum):
    PIAA = "PIAA"
    JSON = "JSON"  # the parsed document
    RAW = "RAW"  # the file, as ingesta published it
    CORRIDA_PARSEO = "CORRIDA_PARSEO"  # the record of a run


class GraphRelation(StrEnum):
    ES = "ES"  # PIAA → JSON
    VIENE_DE = "VIENE_DE"  # JSON → RAW (not composition: re-parsing never deletes the file)


class NodeWrite(StrEnum):
    """data's NodeMode."""

    REPLACE = "replace"
    ENSURE = "ensure"
    MERGE = "merge"


@dataclass(frozen=True)
class NodeKey:
    label: GraphLabel
    id: str


@dataclass(frozen=True)
class GraphNode:
    key: NodeKey
    properties: Properties = field(default_factory=dict)
    mode: NodeWrite = NodeWrite.REPLACE


@dataclass(frozen=True)
class GraphLink:
    type: GraphRelation
    source: NodeKey
    target: NodeKey


@dataclass(frozen=True)
class GraphBatch:
    """Written all or nothing. What hung from `replace_from` (not the node itself) is deleted first."""

    nodes: list[GraphNode]
    links: list[GraphLink] = field(default_factory=list)
    replace_from: NodeKey | None = None
