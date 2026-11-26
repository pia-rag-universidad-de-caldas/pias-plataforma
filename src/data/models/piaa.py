"""PIAA graph model (feature 018): node labels, relationship types and the data that goes in and out.

Every node has a label and a text `id` unique within its label; everything else is free properties. A relationship is
identified by its type and its two ends (there are never two of the same type between the same pair of nodes).
"""

from dataclasses import dataclass, field
from enum import StrEnum

# What Neo4j stores as a property: simple values or homogeneous lists (never maps or mixed lists).
type PropertyValue = str | int | float | bool | list[str] | list[int] | list[float] | list[bool] | None
type Properties = dict[str, PropertyValue]


class Label(StrEnum):
    """Node labels, as in the PIAA graph design. Values go verbatim into Cypher (labels can't be parameters)."""

    CHAT = "CHAT"
    CONSULTA = "CONSULTA"
    JSON = "JSON"
    SECCION = "SECCION"
    FRAGMENTOS = "FRAGMENTOS"
    HALLAZGOS = "HALLAZGOS"
    ANTIPATRON = "ANTIPATRON"
    NORMA = "NORMA"
    FACULTAD = "FACULTAD"
    PROGRAMA = "PROGRAMA"
    ASIGNATURA = "ASIGNATURA"
    PIAA = "PIAA"
    # Chunking experiments (feature 025): their own labels, apart from the production graph above. Since feature 055
    # (part b), an EXP_DOCUMENTO is what one experiment did with one document (EXPERIMENTO → EXP_DOCUMENTO →
    # EXP_SECCION → EXP_CHUNK); the EXP_PUNTUACION of before feature 043 are gone (`migrate-experiments`).
    EXPERIMENTO = "EXPERIMENTO"
    EXP_DOCUMENTO = "EXP_DOCUMENTO"
    EXP_SECCION = "EXP_SECCION"
    EXP_CHUNK = "EXP_CHUNK"
    # Runs of the official chunking (features 041 and 045): the record of each POST /chunking/runs, so that it outlives
    # the server and can be resumed.
    CORRIDA_CHUNKING = "CORRIDA_CHUNKING"
    # Chunking (feature 043): the active configuration (one node).
    CONFIG_OFICIAL = "CONFIG_OFICIAL"
    # Pipeline (feature 028): its templates, runs, cycle iterations and actor events.
    PIPELINE = "PIPELINE"
    PIPE_CORRIDA = "PIPE_CORRIDA"
    PIPE_ITERACION = "PIPE_ITERACION"
    PIPE_EVENTO = "PIPE_EVENTO"
    # Files and parsing (feature 042): the files ingesta publishes, and the record of the parsing runs.
    RAW = "RAW"
    CORRIDA_PARSEO = "CORRIDA_PARSEO"
    # Embeddings (feature 046): the record of its runs and of its experiments over a chunking experiment. An official
    # vector is a property of its FRAGMENTOS, one per model (`embedding_<model>_<dim>`, feature 055); an experiment's
    # is an EXP_EMBED node of its own, one per chunk and embeddings experiment (055).
    CORRIDA_EMBEDDINGS = "CORRIDA_EMBEDDINGS"
    EXP_EMBEDDINGS = "EXP_EMBEDDINGS"
    EXP_EMBED = "EXP_EMBED"
    # Comparisons (feature 060): one question asked to up to four panels (target, embeddings model and LLM each);
    # each panel's CONSULTA hangs from it, without a CHAT.
    COMPARACION = "COMPARACION"


class RelationshipType(StrEnum):
    """Relationship types, as in the PIAA graph design. Values go verbatim into Cypher, like the labels."""

    GENERA = "GENERA"
    SOBRE = "SOBRE"
    TIENE_SECCION = "TIENE_SECCION"
    RESPONDIDA_CON = "RESPONDIDA_CON"
    EN = "EN"
    DE_TIPO = "DE_TIPO"
    INCUMPLE = "INCUMPLE"
    TIENE_FRAGMENTO = "TIENE_FRAGMENTO"
    PERTENECE = "PERTENECE"
    HACE_PARTE = "HACE_PARTE"
    ES = "ES"
    TIENE = "TIENE"
    # Chunking experiments (feature 025; 055 part b: EXP_TIENE_DOCUMENTO and EXP_DE take the place of EXP_GENERA and of
    # the EXP_USA towards a JSON; EXP_USA stays for EXP_EMBEDDINGS → EXPERIMENTO).
    EXP_USA = "EXP_USA"
    EXP_TIENE_DOCUMENTO = "EXP_TIENE_DOCUMENTO"
    EXP_DE = "EXP_DE"
    EXP_TIENE_SECCION = "EXP_TIENE_SECCION"
    EXP_TIENE_CHUNK = "EXP_TIENE_CHUNK"
    # Pipeline (feature 028), and VIENE_DE: an official JSON's link to its RAW (feature 042).
    PIPE_DE = "PIPE_DE"
    PIPE_TIENE_ITERACION = "PIPE_TIENE_ITERACION"
    PIPE_USA = "PIPE_USA"
    PIPE_TIENE_EVENTO = "PIPE_TIENE_EVENTO"
    VIENE_DE = "VIENE_DE"
    # Vectors of embeddings experiments (feature 055): EXP_CHUNK → its EXP_EMBED, and EXP_EMBEDDINGS → the ones it made.
    EXP_TIENE_VECTOR = "EXP_TIENE_VECTOR"
    EXP_GENERA_VECTOR = "EXP_GENERA_VECTOR"
    # Comparisons (feature 060): COMPARACION → the CONSULTA of each panel, with {panel, etiqueta}.
    COMPARA = "COMPARA"


@dataclass(frozen=True)
class RelationshipDefinition:
    """A relationship allowed by the schema: (source)-[type]->(target)."""

    type: RelationshipType
    source: Label
    target: Label


@dataclass(frozen=True)
class NodeRef:
    label: Label
    id: str


@dataclass(frozen=True)
class Node:
    label: Label
    id: str
    properties: Properties  # without `id`, which goes apart


@dataclass(frozen=True)
class Relationship:
    type: RelationshipType
    source: NodeRef
    target: NodeRef
    properties: Properties


# Batch writes (feature 022): a document and everything that hangs from it, in one transaction.


class BatchError(ValueError):
    """A batch that can't be written as sent (for example, a relationship end that doesn't exist). Nothing was
    written."""


class NodeMode(StrEnum):
    """How a batch writes a node that may already exist (MERGE by `id` in both cases)."""

    REPLACE = "replace"  # created, or its properties replaced by the ones sent
    ENSURE = "ensure"  # created with the ones sent if missing; an existing one is not touched
    MERGE = "merge"  # created, or the ones sent set on it and the others kept (feature 025)


@dataclass(frozen=True)
class BatchNode:
    label: Label
    id: str
    properties: Properties = field(default_factory=dict)  # without `id`, which goes apart
    mode: NodeMode = NodeMode.REPLACE


@dataclass(frozen=True)
class BatchResult:
    """What a batch did. Every node sent is in exactly one of created/replaced/kept/merged."""

    deleted: int  # descendants of `replace_from` removed before writing
    created: int  # nodes that didn't exist
    replaced: int  # existing `replace` nodes whose properties were replaced
    kept: int  # existing `ensure` nodes, left as they were
    relationships: int  # relationships merged (created or with their properties replaced)
    merged: int = 0  # existing `merge` nodes that got the properties sent
