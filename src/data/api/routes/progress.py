"""GET /progress/parsing and GET /progress/chunking: how many current files are parsed and how many parsed documents
are chunked, and which ones are missing (or done), a page at a time. Read only."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from data.api.dependencies import Graph, Paginated
from data.api.schemas import NEO4J_DOWN, ProgressPage, error
from data.repository.progress_repository import ProgressRepository

router = APIRouter(prefix="/progress", tags=["progress"])


def _progress(graph: Graph) -> ProgressRepository:
    return ProgressRepository(graph)


Progress = Annotated[ProgressRepository, Depends(_progress)]
_Listed = Annotated[
    Literal["missing", "done"], Query(alias="list", description="which sha256s to list: missing (default) or done")
]


def _page(counts: dict[str, int], listed: str, pagination: Paginated, sha256s: list[str]) -> ProgressPage:
    total = counts["done"] if listed == "done" else counts["total"] - counts["done"]
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
    found = progress.parsing_ids(listed == "done", fingerprint, pagination.skip, pagination.per_page)
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
    never chunked, and the sha256s still to chunk (or, with list=done, the chunked ones), ordered by sha256."""
    counts = progress.chunking_counts(fingerprint)
    found = progress.chunking_ids(listed == "done", fingerprint, pagination.skip, pagination.per_page)
    return _page(counts, listed, pagination, found)
