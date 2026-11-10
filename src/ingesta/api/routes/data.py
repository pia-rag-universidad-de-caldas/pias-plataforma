"""GET /data: the files ready for chunking (vigentes/), filtered and paginated; GET /data/file and
GET /data/content (feature 022): the record and the content of one of them, by its `origen` (the record also by its
`sha256`: at most one chunkable file has each content, since hash duplicates aren't chunkable)."""

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from ingesta.api.dependencies import Categories, Files, Ingest, Runs
from ingesta.api.schemas import ChunkableFiles, Error
from ingesta.config import MAX_PER_PAGE, PER_PAGE
from ingesta.domain import Queries
from ingesta.models import Category, CategoryRepository, FileFilter, FileRecord, FileRepository

router = APIRouter(tags=["data"])

type _Responses = dict[int | str, dict[str, object]]  # `responses=` of a route

_MEMORY_DOWN: _Responses = {503: {"model": Error, "description": "the memory could not be opened"}}
_NOT_CHUNKABLE: _Responses = {
    404: {"model": Error, "description": "the origin isn't registered or isn't ready for chunking"}
}
_DEFAULT_MIME = "application/octet-stream"
_CONTENT: _Responses = {
    200: {"content": {_DEFAULT_MIME: {}}, "description": "the file, with its stored MIME type"},
    500: {"model": Error, "description": "the file could not be read"},
}
_Origin = Annotated[str, Query(description="relative path inside base/, as `origen` in GET /data")]
_ORIGIN_OR_HASH: _Responses = {422: {"model": Error, "description": "not exactly one of origin and sha256"}}


@router.get("/data", responses=_MEMORY_DOWN)
def chunkable_files(
    files: Files,
    categories: Categories,
    runs: Runs,
    type: Annotated[list[str] | None, Query(description="extension; repeatable: ?type=pdf&type=docx")] = None,
    year: int | None = None,
    month: Annotated[int | None, Query(ge=1, le=12, description="month number")] = None,
    week: Annotated[str | None, Query(description="as the folder: Semana_04")] = None,
    code: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=MAX_PER_PAGE)] = PER_PAGE,
) -> ChunkableFiles:
    """All filters must match at once. `reorganizado` is when the last `organizar` run finished: if it changes
    between two requests, the pages may have shifted."""
    filter_ = FileFilter(Queries.normalized_types(type or []), year, month, week, code)
    chunkable = categories.origins_with(Category.CHUNKABLE.value)
    selected = Queries.chunkable(files.all(), chunkable, filter_)
    result = Queries.paginate(selected, page, per_page)
    last_run = runs.last_finished()
    return ChunkableFiles(
        reorganizado=last_run.fin if last_run else None,
        pagina=result.page,
        por_pagina=result.per_page,
        total=result.total,
        paginas=result.pages,
        archivos=result.files,
    )


def _chunkable_record(files: FileRepository, categories: CategoryRepository, origin: str) -> FileRecord:
    """The record of a CHUNKABLE file (as GET /data decides it), or 404."""
    record = files.find(origin) if Queries.is_safe(origin) else None
    if record is None or not Queries.is_safe(record.destino):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"the origin {origin!r} isn't registered")
    if origin not in categories.origins_with(Category.CHUNKABLE.value):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"the origin {origin!r} isn't ready for chunking")
    return record


@router.get("/data/file", responses=_NOT_CHUNKABLE | _ORIGIN_OR_HASH | _MEMORY_DOWN)
def chunkable_file(
    files: Files,
    categories: Categories,
    origin: Annotated[str | None, Query(description="relative path inside base/, as `origen` in GET /data")] = None,
    sha256: Annotated[str | None, Query(description="content hash, as `sha256` in GET /data")] = None,
) -> FileRecord:
    """The record of one chunkable file, the same as its item in GET /data, by its origin or by its sha256 (exactly
    one of the two)."""
    if (origin is None) == (sha256 is None):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "give exactly one of origin and sha256")
    if origin is not None:
        return _chunkable_record(files, categories, origin)
    chunkable = categories.origins_with(Category.CHUNKABLE.value)
    found = Queries.chunkable_with_hash(files.with_hash(sha256 or ""), chunkable)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no file ready for chunking has the sha256 {sha256!r}")
    return found


@router.get(
    "/data/content",
    response_class=StreamingResponse,
    responses=_CONTENT | _NOT_CHUNKABLE | _MEMORY_DOWN,
)
def chunkable_content(files: Files, categories: Categories, ingest: Ingest, origin: _Origin) -> StreamingResponse:
    """The content of one chunkable file (its copy in ingesta/, `destino`), streamed. Content-Type is the MIME type
    stored in the memory (application/octet-stream if unknown)."""
    record = _chunkable_record(files, categories, origin)
    size = ingest.info(record.destino).bytes  # FileError → 500 if the copy is gone
    chunks = ingest.read_chunks(record.destino)
    fallback = record.nombre.encode("ascii", "replace").decode().replace('"', "_")
    disposition = f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(record.nombre)}"
    return StreamingResponse(
        chunks,
        media_type=record.mime or _DEFAULT_MIME,
        headers={"Content-Disposition": disposition, "Content-Length": str(size)},
    )
