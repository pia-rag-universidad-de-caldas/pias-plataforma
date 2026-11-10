"""What consultas writes in the graph, as batches (POST /data/batch). Labels and relationship types are data's (it owns
the schema; a test checks each one is there); their VALUES and the property names stay in Spanish."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

type Properties = Mapping[str, object]  # in practice one of the TypedDicts of stored.py


class GraphLabel(StrEnum):
    CHAT = "CHAT"  # a conversation
    CONSULTA = "CONSULTA"  # a question of it, with its answer
    FRAGMENTOS = "FRAGMENTOS"  # an official chunk it was answered with
    EXP_CHUNK = "EXP_CHUNK"  # a chunk of an embeddings experiment (a laboratory question)
    CONFIG_OFICIAL = "CONFIG_OFICIAL"  # the active configuration (one node per module)


class GraphRelation(StrEnum):
    GENERA = "GENERA"  # CHAT → CONSULTA (composition: data deletes the questions with the chat's replace_from)
    RESPONDIDA_CON = "RESPONDIDA_CON"  # CONSULTA → FRAGMENTOS | EXP_CHUNK, with {puntaje, orden}


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
    mode: NodeWrite = NodeWrite.MERGE


@dataclass(frozen=True)
class GraphLink:
    type: GraphRelation
    source: NodeKey
    target: NodeKey
    properties: Properties = field(default_factory=dict)


@dataclass(frozen=True)
class GraphBatch:
    """Written all or nothing. `replace_from`: data first deletes what hangs from that node through composition
    relationships (a chat's questions, through GENERA; never the chunks they cite)."""

    nodes: list[GraphNode]
    links: list[GraphLink] = field(default_factory=list)
    replace_from: NodeKey | None = None
