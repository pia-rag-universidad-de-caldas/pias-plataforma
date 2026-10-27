"""What chunking writes in the graph: a document and everything under it, as one batch (POST /data/batch).

Labels and relationship types are the ones of data's schema (data owns it); chunking only uses these: the production
chain of feature 023 and the experiment labels of feature 025. Their VALUES and the property names are stored in
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
    # Production graph (feature 023).
    PIAA = "PIAA"
    JSON = "JSON"  # the document
    SECCION = "SECCION"
    FRAGMENTOS = "FRAGMENTOS"  # a chunk
    # Experiments (feature 025): their own labels, never mixed with production.
    EXPERIMENTO = "EXPERIMENTO"
    EXP_DOCUMENTO = "EXP_DOCUMENTO"  # a converted document, shared by every experiment with the same conversion
    EXP_SECCION = "EXP_SECCION"  # a section of a document in one experiment
    EXP_CHUNK = "EXP_CHUNK"
    EXP_PUNTUACION = "EXP_PUNTUACION"  # a score of an experiment


class GraphRelation(StrEnum):
    ES = "ES"  # PIAA → JSON
    TIENE_SECCION = "TIENE_SECCION"  # JSON → SECCION
    TIENE_FRAGMENTO = "TIENE_FRAGMENTO"  # SECCION → FRAGMENTOS
    EXP_USA = "EXP_USA"  # EXPERIMENTO → EXP_DOCUMENTO
    EXP_TIENE_SECCION = "EXP_TIENE_SECCION"  # EXP_DOCUMENTO → EXP_SECCION
    EXP_TIENE_CHUNK = "EXP_TIENE_CHUNK"  # EXP_SECCION → EXP_CHUNK
    EXP_GENERA = "EXP_GENERA"  # EXPERIMENTO → EXP_SECCION
    EXP_TIENE_PUNTUACION = "EXP_TIENE_PUNTUACION"  # EXPERIMENTO → EXP_PUNTUACION
    VIENE_DE = "VIENE_DE"  # official JSON → the EXP_DOCUMENTO it was promoted from (feature 028)


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
