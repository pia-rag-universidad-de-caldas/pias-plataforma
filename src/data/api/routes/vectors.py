"""Vector indexes and the search over them (feature 046): PUT/GET/DELETE /vectors/indexes/{name} and
POST /vectors/search.

data doesn't know which indexes are needed (that depends on the embedding models, which only embeddings knows): it
sets the rules (vector_rules.py) and creates the index embeddings asks for. No index name or dimension is written here.
"""

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from data.api.dependencies import Graph
from data.api.schemas import NEO4J_DOWN, VectorHit, VectorIndex, VectorIndexBody, VectorSearch, error
from data.models import GraphError, GraphRow, GraphValue, Label
from data.repository.cypher import integer
from data.repository.vector_repository import VectorIndexConflict, VectorRepository
from data.schema.vector_rules import MAX_DIMENSIONS, index_problems, valid_index_name

router = APIRouter(prefix="/vectors", tags=["vectors"])

MAX_K = 100
MAX_DOCUMENTS = 200  # of a search over some documents (feature 057): an exact search reads all their chunks
_NOT_FOUND = "there is no vector index with that name (nothing was embedded with that model yet)"


def _repository(graph: Graph) -> VectorRepository:
    return VectorRepository(graph)


Vectors = Annotated[VectorRepository, Depends(_repository)]


def _index(row: GraphRow) -> VectorIndex:
    return VectorIndex(str(row["name"]), str(row["label"]), str(row["property"]), integer(row["dimensions"]))


def _items(value: GraphValue) -> Sequence[GraphValue]:
    return value if isinstance(value, Sequence) and not isinstance(value, str) else []


def _texts(value: GraphValue) -> list[str]:
    return [str(v) for v in _items(value)]


def _integers(value: GraphValue) -> list[int]:
    return [v for v in _items(value) if isinstance(v, int)]


def _hit(row: GraphRow) -> VectorHit:
    score = row["score"]
    if not isinstance(score, (int, float)):
        raise GraphError(f"expected a score and got {score!r}")
    origin, code, activity = row.get("origin"), row.get("code"), row.get("activity")
    return VectorHit(
        id=str(row["id"]),
        score=float(score),
        text=str(row.get("text") or ""),
        headings=_texts(row.get("headings")),
        pages=_integers(row.get("pages")),
        sha256=str(row["sha256"]),
        origin=None if origin is None else str(origin),
        code=None if code is None else str(code),
        activity=None if activity is None else str(activity),
    )


def _not_found(index: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"there is no vector index {index!r}")


@router.put(
    "/indexes/{name}",
    responses={
        409: error("an index with that name, or another one on that label, exists with another definition"),
        422: error("invalid name, dimensions or label"),
        503: error(NEO4J_DOWN),
    },
)
def ensure_index(vectors: Vectors, name: str, body: VectorIndexBody) -> VectorIndex:
    """Creates the vector index (cosine, on `property`) if missing; an existing one must be the same. Idempotent."""
    problems = index_problems(name, body.label, body.dimensions, body.property)
    if problems:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "; ".join(problems))
    try:
        return _index(vectors.ensure(name, body.label, body.property, body.dimensions))
    except VectorIndexConflict as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e


@router.get("/indexes/{name}", responses={404: error(_NOT_FOUND), 503: error(NEO4J_DOWN)})
def read_index(vectors: Vectors, name: str) -> VectorIndex:
    found = vectors.find(name) if valid_index_name(name) else None
    if found is None:
        raise _not_found(name)
    return _index(found)


@router.delete(
    "/indexes/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: error(_NOT_FOUND), 503: error(NEO4J_DOWN)},
)
def drop_index(
    vectors: Vectors,
    name: str,
    drop_property: Annotated[bool, Query(description="also remove the index's property from its nodes")] = False,
) -> None:
    """Drops the index; the vectors stay on their nodes unless `drop_property` (feature 055: that model's vectors go
    too, from every node of the index's label)."""
    if not valid_index_name(name) or vectors.drop(name, drop_property) is None:
        raise _not_found(name)


@router.post(
    "/search",
    responses={
        404: error(_NOT_FOUND),
        422: error(
            "not a FRAGMENTOS index (EXP_EMBED with experiment), a vector of other dimensions, or k out of range"
        ),
        503: error(NEO4J_DOWN),
    },
)
def search(vectors: Vectors, body: VectorSearch) -> list[VectorHit]:
    """The official chunks (FRAGMENTOS of a chunked JSON) closest to the vector, best first. With `experiment`, the
    EXP_CHUNK whose vector that embeddings experiment calculated (features 048 and 055), in an EXP_EMBED index: each
    hit is the chunk, not its EXP_EMBED. With `sha256s` (feature 057), only the chunks of those documents, by the
    index's vectors: an exact search, with the same score."""
    if not 1 <= body.k <= MAX_K:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"k must be between 1 and {MAX_K}")
    if not 1 <= len(body.vector) <= MAX_DIMENSIONS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"the vector must have 1 to {MAX_DIMENSIONS} values")
    found = vectors.find(body.index) if valid_index_name(body.index) else None
    if found is None:
        raise _not_found(body.index)
    wanted = Label.FRAGMENTOS if body.experiment is None else Label.EXP_EMBED
    if found["label"] != wanted.value:
        reads = "the search" if body.experiment is None else "the search of an experiment"
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{reads} reads {wanted.value}: not that index")
    if len(body.vector) != integer(found["dimensions"]):  # Neo4j would refuse it, and that would be a 503
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"the index has {found['dimensions']} dimensions")
    if body.sha256s is not None and body.experiment is not None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "sha256s are official documents: not with experiment"
        )
    if body.sha256s is not None and not 1 <= len(body.sha256s) <= MAX_DOCUMENTS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"sha256s must have 1 to {MAX_DOCUMENTS} documents")
    if body.sha256s is not None:
        rows = vectors.search_documents(str(found["property"]), body.vector, body.k, body.sha256s)
    elif body.experiment is None:
        rows = vectors.search(body.index, body.vector, body.k)
    else:
        rows = vectors.search_experiment(body.index, body.vector, body.k, body.experiment)
    return [_hit(row) for row in rows]
