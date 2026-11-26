"""What chunking writes in the graph: a document and everything under it, as one batch (POST /data/batch).

Labels and relationship types are the ones of data's schema (data owns it); chunking only uses these: what hangs from
a JSON in production and the experiment labels (feature 043). Their VALUES and the property names are stored in
Neo4j: they stay in Spanish.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

# What Neo4j stores as a property: simple values or homogeneous lists.
type PropertyValue = str | int | float | bool | list[str] | list[int] | None
# The properties of a node or relationship: one of the TypedDicts of stored.py (a TypedDict is only a
# Mapping[str, object]).
type Properties = Mapping[str, object]


class GraphLabel(StrEnum):
    # Production graph (feature 023): the JSON is written by parsing (feature 042); chunking adds what hangs from it.
    JSON = "JSON"  # the document
    SECCION = "SECCION"
    FRAGMENTOS = "FRAGMENTOS"  # a chunk
    # Experiments (feature 043): their own labels, never mixed with production.
    EXPERIMENTO = "EXPERIMENTO"
    EXP_DOCUMENTO = "EXP_DOCUMENTO"  # what one experiment did with one document (feature 055 part b)
    EXP_SECCION = "EXP_SECCION"  # a heading path of a document in one experiment
    EXP_CHUNK = "EXP_CHUNK"
    CONFIG_OFICIAL = "CONFIG_OFICIAL"  # the active configuration (one node)
    CORRIDA_CHUNKING = "CORRIDA_CHUNKING"  # the record of a POST /runs (feature 045)


class GraphRelation(StrEnum):
    TIENE_SECCION = "TIENE_SECCION"  # JSON → SECCION
    TIENE_FRAGMENTO = "TIENE_FRAGMENTO"  # SECCION → FRAGMENTOS
    EXP_TIENE_DOCUMENTO = "EXP_TIENE_DOCUMENTO"  # EXPERIMENTO → EXP_DOCUMENTO (feature 055 part b)
    EXP_DE = "EXP_DE"  # EXP_DOCUMENTO → JSON (not composition: the official document stays)
    EXP_TIENE_SECCION = "EXP_TIENE_SECCION"  # EXP_DOCUMENTO → EXP_SECCION
    EXP_TIENE_CHUNK = "EXP_TIENE_CHUNK"  # EXP_SECCION → EXP_CHUNK
    # Only read, never written by chunking: what depends on an experiment (feature 055 part b, 409 when deleting it).
    EXP_USA = "EXP_USA"  # EXP_EMBEDDINGS → EXPERIMENTO (an embeddings experiment over its chunks)
    PIPE_USA = "PIPE_USA"  # PIPE_ITERACION → EXPERIMENTO (a pipeline run that links it)


class NodeWrite(StrEnum):
    """How a batch writes a node that may already exist (data's NodeMode; MERGE by id in every case)."""

    REPLACE = "replace"  # its properties become the ones sent
    ENSURE = "ensure"  # created with the ones sent if missing; an existing one is not touched
    MERGE = "merge"  # the ones sent are set, the others kept


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
    properties: Properties = field(default_factory=dict)


@dataclass(frozen=True)
class GraphBatch:
    """Written all or nothing. What hung from `replace_from` (not the node itself) is deleted first."""

    nodes: list[GraphNode]
    links: list[GraphLink]
    replace_from: NodeKey | None = None
