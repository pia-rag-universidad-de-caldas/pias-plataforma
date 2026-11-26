"""GET /progress/parsing, /progress/chunking and /progress/embeddings: how many current files are parsed, how many
parsed documents are chunked and how many chunked ones have a model's vectors, and which ones are missing (or done), a
page at a time. Read only."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from data.api.dependencies import Graph, Paginated
from data.api.schemas import NEO4J_DOWN, ProgressPage, error
from data.repository.progress_repository import ProgressRepository
from data.schema.vector_rules import valid_vector_property

router = APIRouter(prefix="/progress", tags=["progress"])


def _progress(graph: Graph) -> ProgressRepository:
    return ProgressRepository(graph)


Progress = Annotated[ProgressRepository, Depends(_progress)]
type Listing = Literal["missing", "done", "all"]
_Listed = Annotated[
    Listing,
    Query(alias="list", description="which sha256s to list: missing (default), done or all of them (feature 059)"),
]
_DONE: dict[str, bool | None] = {"missing": False, "done": True, "all": None}


def _page(counts: dict[str, int], listed: str, pagination: Paginated, sha256s: list[str]) -> ProgressPage:
    listed_total = {"done": counts["done"], "all": counts["total"]}
    total = listed_total.get(listed, counts["total"] - counts["done"])
    return ProgressPage(
        total=counts["total"],
        done=counts["done"],
        missing=counts["total"] - counts["done"],
        partial=counts["partial"],
        errors=counts["errors"],
        never=counts["never"],
        listed=listed,
        page=pagination.page,
        per_page=pagination.per_page,
        pages=pagination.pages(total),
        sha256s=sha256s,
    )


@router.get("/parsing", responses={503: error(NEO4J_DOWN)})
def parsing_progress(
    progress: Progress,
    pagination: Paginated,
    listed: _Listed = "missing",
    fingerprint: Annotated[
        str | None, Query(description="GET /parsing/config's: one parsed with another fingerprint counts as missing")
    ] = None,
) -> ProgressPage:
    """Over the current RAW nodes: how many are parsed (estado_parseo parseado), partial, in error or never parsed,
    and the sha256s still to parse (or, with list=done, the parsed ones)."""
    counts = progress.parsing_counts(fingerprint)
    found = progress.parsing_ids(_DONE[listed], fingerprint, pagination.skip, pagination.per_page)
    return _page(counts, listed, pagination, found)


@router.get("/chunking", responses={503: error(NEO4J_DOWN)})
def chunking_progress(
    progress: Progress,
    pagination: Paginated,
    listed: _Listed = "missing",
    fingerprint: Annotated[
        str | None,
        Query(
            description="GET /chunking/config's: one chunked with another configuration, or over another parse, counts"
            " as missing"
        ),
    ] = None,
) -> ProgressPage:
    """Over the parsed JSON nodes: how many have their chunks (estado_chunking fragmentado), how many failed or were
    never chunked, and the sha256s still to chunk (or, with list=done, the chunked ones; with list=all, every parsed
    one), ordered by sha256."""
    counts = progress.chunking_counts(fingerprint)
    found = progress.chunking_ids(_DONE[listed], fingerprint, pagination.skip, pagination.per_page)
    return _page(counts, listed, pagination, found)


@router.get(
    "/experiment-embeddings",
    responses={404: error("there is no embeddings experiment with that id"), 503: error(NEO4J_DOWN)},
)
def experiment_embeddings_progress(
    progress: Progress,
    pagination: Paginated,
    experiment: Annotated[str, Query(description="the id of an embeddings experiment (EXP_EMBEDDINGS)")],
    listed: _Listed = "missing",
) -> ProgressPage:
    """Feature 062: over the chunked documents of the chunking experiment it embeds (EXP_USA), how many have every
    chunk with a vector of that embeddings experiment, and the sha256s still to embed (added afterwards, chunked
    again or left halfway), ordered by sha256."""
    if not progress.embeddings_experiment_exists(experiment):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"there is no embeddings experiment with id {experiment!r}")
    counts = progress.experiment_embedding_counts(experiment)
    found = progress.experiment_embedding_ids(_DONE[listed], experiment, pagination.skip, pagination.per_page)
    return _page(counts, listed, pagination, found)


@router.get("/embeddings", responses={422: error("not a vector property"), 503: error(NEO4J_DOWN)})
def embeddings_progress(
    progress: Progress,
    pagination: Paginated,
    property: Annotated[
        str, Query(description="the model's vector property, embedding_<model>_<dim> (GET /embeddings/config's)")
    ],
    listed: _Listed = "missing",
) -> ProgressPage:
    """Over the chunked JSON nodes: how many have that model's vectors over the chunks they have now, how many were
    embedded over other chunks (`partial`: chunked again since, or embedded before this was recorded) or never, and
    the sha256s still to embed (or, with list=done, the embedded ones), ordered by sha256."""
    if not valid_vector_property(property):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "property must be embedding_<model>_<dimensions>")
    counts = progress.embedding_counts(property)
    found = progress.embedding_ids(_DONE[listed], property, pagination.skip, pagination.per_page)
    return _page(counts, listed, pagination, found)
