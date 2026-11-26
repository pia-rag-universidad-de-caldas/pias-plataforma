"""Request and response bodies of the graph API (those that aren't already a data.models model)."""

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from common.api import Error
from data.config import MAX_PER_PAGE
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
    """GET /progress/parsing, /chunking and /embeddings: the counts and a page of the listed sha256s."""

    total: int  # current RAW (parsing), parsed JSON (chunking) or chunked JSON (embeddings)
    done: int  # parsed / chunked
    missing: int  # total - done
    partial: int  # parsing: parsed only in part; embeddings: over other chunks (they count as missing)
    errors: int  # its last try failed (they count as missing)
    never: int  # never tried
    listed: str  # missing, done or all (the ?list= asked): what sha256s holds
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
    sha256s: list[str] | None = None  # only the chunks of these official documents (feature 057; not with experiment)


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
    activity: str | None = None  # the course, as embeddings read it from the PIAA's header (feature 057)


@dataclass(frozen=True)
class DocumentSearch:
    """Body of POST /documents/search (feature 057): the words of a text against the course of each document."""

    text: str
    k: int = 10


@dataclass(frozen=True)
class DocumentHit:
    """A chunked document whose course (`name`, `activity_code`) matches the text, with Lucene's score."""

    sha256: str
    score: float
    name: str | None  # actividad: the course's name, as embeddings read it from the PIAA's header
    activity_code: str | None  # codigo_actividad: 0100105, G6K0346...
    origin: str | None
    code: str | None  # the PIAA's code (the folder of the corpus)


# Selections of documents (feature 062): which documents the pipeline hands to chunking and embeddings.


class PageSpan(BaseModel):
    """`{from, to}`: pages of `per_page`, both included, from 1."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    start: int = Field(alias="from", ge=1)
    end: int = Field(alias="to", ge=1)


class FileSelection(BaseModel):
    """Exactly one mode: `all`, `sha256s`, `pages` (with `per_page`) or `sample` (with an optional `seed`: then the
    sample repeats). The filters are those of the document's RAW and go with `all`, `pages` or `sample`; `month` only
    with `year`, `week` only with `month`."""

    model_config = ConfigDict(extra="forbid")

    all: bool = False
    sha256s: list[str] = Field(default_factory=list)
    pages: PageSpan | None = None
    per_page: int | None = Field(default=None, ge=1)
    sample: int | None = Field(default=None, ge=1)
    seed: int | None = None
    types: list[str] = Field(default_factory=list)  # the RAW's `tipo`: pdf, docx, doc
    year: int | None = None  # anio
    month: int | None = Field(default=None, ge=1, le=12)  # the leading number of `mes` (11_Noviembre)
    week: str | None = None  # semana, as stored (Semana_02)


class DocumentSelect(BaseModel):
    """Body of POST /documents/select: the documents of a universe that follow `files`, a page of the answer at a
    time (`page`, `per_page`: of the selected sha256s, not the `pages` of `files`)."""

    model_config = ConfigDict(extra="forbid")

    universe: Literal["parsed", "chunked"]
    files: FileSelection
    exclude_experiment: str | None = None  # without those this chunking experiment already has (its EXP_DOCUMENTO)
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=MAX_PER_PAGE, ge=1, le=MAX_PER_PAGE)


@dataclass(frozen=True)
class SelectedDocuments:
    total: int  # documents the selection takes, across all the pages
    sha256s: list[str]  # those of the page asked for, ordered by sha256
    pages: int  # of per_page
