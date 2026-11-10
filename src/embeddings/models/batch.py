"""What embeddings writes in the graph, as batches (POST /data/batch). Labels and relationship types are data's (it
owns the schema; a test checks each one is there); their VALUES and the property names stay in Spanish."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

type Properties = Mapping[str, object]  # in practice built from the TypedDicts of stored.py


class GraphLabel(StrEnum):
    JSON = "JSON"  # the official document (parsing's, chunked by chunking)
    SECCION = "SECCION"
    FRAGMENTOS = "FRAGMENTOS"  # the official chunks: they get their vector, one property per model
    EXPERIMENTO = "EXPERIMENTO"  # a chunking experiment
    EXP_SECCION = "EXP_SECCION"
    EXP_CHUNK = "EXP_CHUNK"  # its chunks
    EXP_EMBED = "EXP_EMBED"  # the vector an embeddings experiment calculated for one of them (feature 055)
    CONFIG_OFICIAL = "CONFIG_OFICIAL"  # the active configuration (one node per module)
    CORRIDA_EMBEDDINGS = "CORRIDA_EMBEDDINGS"  # the record of a production run
    EXP_EMBEDDINGS = "EXP_EMBEDDINGS"  # the record of an experiment


class GraphRelation(StrEnum):
    TIENE_SECCION = "TIENE_SECCION"  # JSON → SECCION
    TIENE_FRAGMENTO = "TIENE_FRAGMENTO"  # SECCION → FRAGMENTOS
    EXP_GENERA = "EXP_GENERA"  # EXPERIMENTO → EXP_SECCION
    EXP_TIENE_CHUNK = "EXP_TIENE_CHUNK"  # EXP_SECCION → EXP_CHUNK
    EXP_USA = "EXP_USA"  # EXP_EMBEDDINGS → EXPERIMENTO (not composition: deleting it never deletes the chunks)
    EXP_TIENE_VECTOR = "EXP_TIENE_VECTOR"  # EXP_CHUNK → EXP_EMBED (composition, feature 055)
    EXP_GENERA_VECTOR = "EXP_GENERA_VECTOR"  # EXP_EMBEDDINGS → EXP_EMBED (composition, feature 055)


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


@dataclass(frozen=True)
class GraphBatch:
    """Written all or nothing. Saving vectors deletes nothing; only deleting an embeddings experiment has a
    replace_from (its EXP_EMBEDDINGS: its EXP_EMBED go, nothing else)."""

    nodes: list[GraphNode]
    links: list[GraphLink] = field(default_factory=list)
    replace_from: NodeKey | None = None
