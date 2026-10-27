"""GET /documents, /documents/{sha256} and /documents/{sha256}/chunks (feature 023): what is in the graph, read
through data over HTTP (chunking never opens Neo4j)."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from chunking.api.dependencies import Catalog
from chunking.api.schemas import Error
from chunking.config import MAX_PER_PAGE, PER_PAGE
from chunking.models import DocumentChunks, DocumentPage, ProcessedDocument

router = APIRouter(prefix="/documents", tags=["documents"])

type _Responses = dict[int | str, dict[str, object]]  # `responses=` of a route

_DATA_DOWN: _Responses = {503: {"model": Error, "description": "data (or Neo4j) is not answering"}}
_NOT_FOUND: _Responses = {404: {"model": Error, "description": "no document with that sha256 in the graph"}}


def _document(catalog: Catalog, sha256: str) -> ProcessedDocument:
    document = catalog.document(sha256)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"there is no document with sha256 {sha256!r} in the graph")
    return document


@router.get("", responses=_DATA_DOWN)
def list_documents(
    catalog: Catalog,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=MAX_PER_PAGE)] = PER_PAGE,
) -> DocumentPage:
    """The documents in the graph (chunked or in error), ordered by sha256."""
    return catalog.documents(page, per_page)


@router.get("/{sha256}", responses=_NOT_FOUND | _DATA_DOWN)
def read_document(catalog: Catalog, sha256: str) -> ProcessedDocument:
    return _document(catalog, sha256)


@router.get("/{sha256}/chunks", responses=_NOT_FOUND | _DATA_DOWN)
def document_chunks(catalog: Catalog, sha256: str) -> DocumentChunks:
    """The document with its sections and its chunks, in order (each with its headings, pages and tokens)."""
    document = _document(catalog, sha256)
    sections, chunks = catalog.chunks(sha256)
    return DocumentChunks(document, sections, chunks)
