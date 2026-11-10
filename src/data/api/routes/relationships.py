"""Relationship CRUD: /relationships[/{type}/{source_label}/{source_id}/{target_label}/{target_id}].

A relationship is identified by its type and its two ends; only the schema's (data.schema) are allowed, otherwise 422.
"""

from fastapi import APIRouter, HTTPException, status

from data.api.dependencies import Key, Paginated, RelationshipKey, Repository, allowed_relationship
from data.api.schemas import NEO4J_DOWN, NewRelationship, PropertiesChange, RelationshipPage, error
from data.models import Relationship, RelationshipType

router = APIRouter(prefix="/relationships", tags=["relationships"])

_RELATIONSHIP = "/{type}/{source_label}/{source_id}/{target_label}/{target_id}"
_NOT_FOUND = "there is no relationship of that type between those nodes"
_NOT_ALLOWED = "the schema doesn't allow that type between those labels"
_MISSING_END = "the source or the target node is missing"


def _not_found(key: RelationshipKey) -> HTTPException:
    d = key.definition
    return HTTPException(
        status.HTTP_404_NOT_FOUND, f"there is no ({d.source} {key.source!r})-[:{d.type}]->({d.target} {key.target!r})"
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    responses={
        404: error(_MISSING_END),
        409: error("there is already a relationship of that type between those nodes"),
        422: error(_NOT_ALLOWED),
        503: error(NEO4J_DOWN),
    },
)
def create_relationship(repository: Repository, new: NewRelationship) -> Relationship:
    definition = allowed_relationship(new.type, new.source.label, new.target.label)
    for end in (new.source, new.target):
        if repository.node(end.label, end.id) is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"there is no {end.label} node with id {end.id!r}")
    if repository.relationship(definition, new.source.id, new.target.id) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "there is already a relationship of that type between those nodes"
        )
    created = repository.create_relationship(definition, new.source.id, new.target.id, new.properties)
    if created is None:  # someone deleted an end between the check and the creation
        raise HTTPException(status.HTTP_404_NOT_FOUND, _MISSING_END)
    return created


@router.get("/{type}", responses={503: error(NEO4J_DOWN)})
def list_relationships(repository: Repository, pagination: Paginated, type: RelationshipType) -> RelationshipPage:
    """The type's relationships, ordered by their ends. A page past the last one returns an empty list."""
    total = repository.count_relationships(type)
    return RelationshipPage(
        page=pagination.page,
        per_page=pagination.per_page,
        total=total,
        pages=pagination.pages(total),
        relationships=repository.relationships(type, pagination.skip, pagination.per_page),
    )


_RESPONSES: dict[int | str, dict[str, object]] = {
    404: error(_NOT_FOUND),
    422: error(_NOT_ALLOWED),
    503: error(NEO4J_DOWN),
}


@router.get(_RELATIONSHIP, responses=_RESPONSES)
def read_relationship(repository: Repository, key: Key) -> Relationship:
    relationship = repository.relationship(key.definition, key.source, key.target)
    if relationship is None:
        raise _not_found(key)
    return relationship


@router.put(_RELATIONSHIP, responses=_RESPONSES)
def replace_relationship(repository: Repository, key: Key, change: PropertiesChange) -> Relationship:
    """Replaces all the relationship's properties (the ones not sent are removed)."""
    relationship = repository.update_relationship(key.definition, key.source, key.target, change.properties, True)
    if relationship is None:
        raise _not_found(key)
    return relationship


@router.patch(_RELATIONSHIP, responses=_RESPONSES)
def update_relationship(repository: Repository, key: Key, change: PropertiesChange) -> Relationship:
    """Changes only the properties sent; one with a null value is removed."""
    relationship = repository.update_relationship(key.definition, key.source, key.target, change.properties, False)
    if relationship is None:
        raise _not_found(key)
    return relationship


@router.delete(_RELATIONSHIP, status_code=status.HTTP_204_NO_CONTENT, responses=_RESPONSES)
def delete_relationship(repository: Repository, key: Key) -> None:
    """Deletes the relationship; the nodes stay."""
    if not repository.delete_relationship(key.definition, key.source, key.target):
        raise _not_found(key)
