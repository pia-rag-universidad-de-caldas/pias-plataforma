"""Route dependencies: the settings, the graph and the parameters shared by several routes.

Unlike the ingesta memory, the graph adapter is a single one for the whole app: the Neo4j driver keeps a connection
pool and can be shared across threads. The app lifespan closes it.
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Query, Request, status

from data.config import MAX_PER_PAGE, PER_PAGE
from data.models import GraphAdapter, Label, RelationshipDefinition, RelationshipType
from data.repository import PiaaRepository
from data.schema import allowed, definition


@dataclass(frozen=True)
class ApiSettings:
    url: str  # Neo4j URL (no password: only the adapter has it)
    user: str
    database: str | None  # database inside the server; None = the default one


@dataclass(frozen=True)
class Pagination:
    page: int  # from 1
    per_page: int

    @property
    def skip(self) -> int:
        return (self.page - 1) * self.per_page

    def pages(self, total: int) -> int:
        return -(-total // self.per_page)


@dataclass(frozen=True)
class RelationshipKey:
    """A relationship as given by the route: its schema definition and the ids of its ends."""

    definition: RelationshipDefinition
    source: str
    target: str


def allowed_relationship(type: RelationshipType, source: Label, target: Label) -> RelationshipDefinition:
    """The schema definition, or 422 listing the combinations that type does allow."""
    found = definition(type, source, target)
    if found is None:
        valid = ", ".join(f"({d.source})-[:{d.type}]->({d.target})" for d in allowed(type))
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"the schema doesn't allow ({source})-[:{type}]->({target}); {type} only allows {valid}",
        )
    return found


def _settings(request: Request) -> ApiSettings:
    settings: ApiSettings = request.app.state.settings
    return settings


def _graph(request: Request) -> GraphAdapter:
    graph: GraphAdapter = request.app.state.graph
    return graph


def _repository(graph: Annotated[GraphAdapter, Depends(_graph)]) -> PiaaRepository:
    return PiaaRepository(graph)


def _pagination(
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=MAX_PER_PAGE)] = PER_PAGE,
) -> Pagination:
    return Pagination(page, per_page)


def _relationship_key(
    type: RelationshipType, source_label: Label, source_id: str, target_label: Label, target_id: str
) -> RelationshipKey:
    return RelationshipKey(allowed_relationship(type, source_label, target_label), source_id, target_id)


# Types for route parameters: `def route(repository: Repository) -> ...`.
Settings = Annotated[ApiSettings, Depends(_settings)]
Graph = Annotated[GraphAdapter, Depends(_graph)]
Repository = Annotated[PiaaRepository, Depends(_repository)]
Paginated = Annotated[Pagination, Depends(_pagination)]  # ?page=1&per_page=50
Key = Annotated[RelationshipKey, Depends(_relationship_key)]  # /{type}/{source_label}/{source_id}/...
