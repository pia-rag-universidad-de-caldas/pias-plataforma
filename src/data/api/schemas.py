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
