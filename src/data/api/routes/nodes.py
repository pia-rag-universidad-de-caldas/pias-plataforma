"""Node CRUD: /nodes/{label}[/{id}]. A node is identified by its label and its id."""

from uuid import uuid4

from fastapi import APIRouter, HTTPException, status

from data.api.dependencies import Paginated, Repository
from data.api.schemas import NEO4J_DOWN, NewNode, NodePage, PropertiesChange, error
from data.models import Label, Node, Relationship

router = APIRouter(prefix="/nodes", tags=["nodes"])

_NOT_FOUND = "there is no node with that label and id"


def _not_found(label: Label, id: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"there is no {label} node with id {id!r}")


@router.get("/{label}", responses={503: error(NEO4J_DOWN)})
def list_nodes(repository: Repository, pagination: Paginated, label: Label) -> NodePage:
    """The label's nodes, ordered by id. A page past the last one returns an empty list."""
    total = repository.count_nodes(label)
    return NodePage(
        page=pagination.page,
        per_page=pagination.per_page,
        total=total,
        pages=pagination.pages(total),
        nodes=repository.nodes(label, pagination.skip, pagination.per_page),
    )


@router.post(
    "/{label}",
    status_code=status.HTTP_201_CREATED,
    responses={409: error("there is already a node with that label and id"), 503: error(NEO4J_DOWN)},
)
def create_node(repository: Repository, label: Label, new: NewNode) -> Node:
    id = new.id or uuid4().hex
    if repository.node(label, id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"there is already a {label} node with id {id!r}")
    return repository.create_node(label, id, new.properties)


@router.get("/{label}/{id}", responses={404: error(_NOT_FOUND), 503: error(NEO4J_DOWN)})
def read_node(repository: Repository, label: Label, id: str) -> Node:
    node = repository.node(label, id)
    if node is None:
        raise _not_found(label, id)
    return node


@router.put("/{label}/{id}", responses={404: error(_NOT_FOUND), 503: error(NEO4J_DOWN)})
def replace_node(repository: Repository, label: Label, id: str, change: PropertiesChange) -> Node:
    """Replaces all the properties (the ones not sent are removed). The id stays."""
    node = repository.update_node(label, id, change.properties, replace=True)
    if node is None:
        raise _not_found(label, id)
    return node


@router.patch("/{label}/{id}", responses={404: error(_NOT_FOUND), 503: error(NEO4J_DOWN)})
def update_node(repository: Repository, label: Label, id: str, change: PropertiesChange) -> Node:
    """Changes only the properties sent; one with a null value is removed. The id stays."""
    node = repository.update_node(label, id, change.properties, replace=False)
    if node is None:
        raise _not_found(label, id)
    return node


@router.delete(
    "/{label}/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: error(_NOT_FOUND), 503: error(NEO4J_DOWN)},
)
def delete_node(repository: Repository, label: Label, id: str) -> None:
    """Deletes the node together with all its relationships."""
    if not repository.delete_node(label, id):
        raise _not_found(label, id)


@router.get("/{label}/{id}/relationships", responses={404: error(_NOT_FOUND), 503: error(NEO4J_DOWN)})
def node_relationships(repository: Repository, label: Label, id: str) -> list[Relationship]:
    """The relationships coming into or out of the node."""
    if repository.node(label, id) is None:
        raise _not_found(label, id)
    return repository.node_relationships(label, id)
