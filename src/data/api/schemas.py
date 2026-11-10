"""Request and response bodies of the graph API (those that aren't already a data.models model)."""

from dataclasses import dataclass, field

from common.api import Error
from data.models import (
    BatchNode,
    Label,
    Node,
    NodeRef,
    Properties,
    Relationship,
    RelationshipDefinition,
    RelationshipType,
)

NEO4J_DOWN = "Neo4j is not answering or rejected the query"


def error(description: str) -> dict[str, object]:
    """One `responses=` entry of a route: {"detail"} body with its description."""
    return {"model": Error, "description": description}


@dataclass(frozen=True)
class HealthStatus:
    status: str
    version: str
    neo4j: str  # server URL


@dataclass(frozen=True)
class Schema:
    labels: list[Label]
    relationships: list[RelationshipDefinition]


@dataclass(frozen=True)
class NewNode:
    """Body of POST /nodes/{label}. Without `id`, one is generated (uuid4 in hex)."""

    id: str | None = None
    properties: Properties = field(default_factory=dict)


@dataclass(frozen=True)
class PropertiesChange:
    """Body of PUT (replaces all the properties) and PATCH (only the ones sent; null removes one)."""

    properties: Properties


@dataclass(frozen=True)
class NewRelationship:
    """Body of POST /relationships: (source)-[type]->(target), which the schema must allow."""

    type: RelationshipType
    source: NodeRef
    target: NodeRef
    properties: Properties = field(default_factory=dict)


@dataclass(frozen=True)
class NodePage:
    page: int
    per_page: int
    total: int  # nodes with the label, across all pages
    pages: int
    nodes: list[Node]


@dataclass(frozen=True)
class ProgressPage:
    """GET /progress/parsing and /progress/chunking: the counts and a page of the listed sha256s."""

    total: int  # current RAW (parsing) or parsed JSON (chunking)
    done: int  # parsed / chunked
    missing: int  # total - done
    partial: int  # parsing: parsed only in part (they count as missing)
    errors: int  # its last try failed (they count as missing)
    never: int  # never tried
    listed: str  # missing or done (the ?list= asked): what sha256s holds
    page: int
    per_page: int
    pages: int  # of the listed ones
    sha256s: list[str]


@dataclass(frozen=True)
class RelationshipPage:
    page: int
    per_page: int
    total: int  # relationships of the type, across all pages
    pages: int
    relationships: list[Relationship]


@dataclass(frozen=True)
class Batch:
    """Body of POST /batch: a document and everything that hangs from it, written all or nothing. Each relationship
    end must be one of `nodes` or already exist in the graph."""

    nodes: list[BatchNode] = field(default_factory=list)
    relationships: list[NewRelationship] = field(default_factory=list)
    replace_from: NodeRef | None = None  # its descendants (not the node itself) are deleted before writing


# Vector indexes and their search (feature 046): embeddings asks for them; data creates them and runs the query.


@dataclass(frozen=True)
class VectorIndexBody:
    """Body of PUT /vectors/indexes/{name}: over which nodes, which property and how many dimensions."""

    label: Label  # FRAGMENTOS or EXP_EMBED
    property: str  # embedding_<model>_<dim> (feature 055): one per model, so models live side by side
    dimensions: int


@dataclass(frozen=True)
class VectorIndex:
    name: str
    label: str
    property: str  # embedding_<model>_<dim>
    dimensions: int


@dataclass(frozen=True)
class VectorSearch:
    """Body of POST /vectors/search: a vector of the index's dimensions."""

    index: str
    vector: list[float]
    k: int = 5
    experiment: str | None = None  # an embeddings experiment: then the index is an EXP_EMBED one (features 048, 055)


@dataclass(frozen=True)
class VectorHit:
    """A chunk (FRAGMENTOS, or EXP_CHUNK of an experiment) and how close it is (cosine, 0 to 1)."""

    id: str
    score: float
    text: str
    headings: list[str]
    pages: list[int]
    sha256: str
    origin: str | None  # from the RAW the JSON came from (None if it has none)
    code: str | None
