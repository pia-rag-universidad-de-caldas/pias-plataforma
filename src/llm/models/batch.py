"""What llm writes in the graph, as batches (POST /data/batch): only its CONFIG_OFICIAL node. The label is data's (it
owns the schema; a test checks it is there); the property names stay in Spanish."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

type Properties = Mapping[str, object]  # in practice the TypedDict of stored.py


class GraphLabel(StrEnum):
    CONFIG_OFICIAL = "CONFIG_OFICIAL"  # the active configuration (one node per module)


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
    mode: NodeWrite = NodeWrite.MERGE  # as embeddings: every key of the configuration is sent each time


@dataclass(frozen=True)
class GraphBatch:
    nodes: list[GraphNode]
