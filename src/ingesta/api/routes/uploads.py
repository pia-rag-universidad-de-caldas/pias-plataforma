"""POST /uploads and GET /uploads (feature 049): files uploaded to base/ through the API (the front, 052), and the
record of what was uploaded. Uploading doesn't ingest: the front then asks for POST /pipeline/runs
{"template": "produccion", "scope": "new"}, which ingests, parses, chunks and embeds what is new."""

import logging
import threading
from collections import Counter
from collections.abc import Sequence
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, status
from starlette.concurrency import run_in_threadpool

from ingesta.adapters import LocalFileAdapter, create_adapter
from ingesta.api.dependencies import ApiSettings, Settings, Uploaded
from ingesta.api.multipart import MultipartError, boundary, parse
from ingesta.api.schemas import Error
from ingesta.domain import Uploads
from ingesta.models import IncomingFile, Upload, UploadResult, UploadState
from ingesta.repository import DbFileRepository, DbUploadRepository
from ingesta.tables import TABLES

router = APIRouter(tags=["uploads"])
LOG = logging.getLogger(__name__)

FILES_FIELDS = ("files", "files[]")  # the field of the files (a browser's FormData often names it files[])
CODE_FIELD = "code"

_FORM = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["files", CODE_FIELD],
                    "properties": {
                        "files": {"type": "array", "items": {"type": "string", "format": "binary"}},
                        CODE_FIELD: {"type": "string", "pattern": r"^\d{6}$", "description": "PIAA code; 000000: none"},
                    },
                }
            }
        },
    }
}


def _incoming(content_type: str, body: bytes) -> tuple[str, list[IncomingFile]]:
    """The code and the files of the form, or the error that refuses the whole upload."""
    mark = boundary(content_type)
    if mark is None:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "send multipart/form-data with files and code")
    try:
        parts = parse(body, mark)
    except MultipartError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"malformed multipart body: {e}") from e
    codes = [p.content.decode("utf-8", errors="replace").strip() for p in parts if p.name == CODE_FIELD]
    files = [IncomingFile(p.filename or "", p.content) for p in parts if p.name in FILES_FIELDS]
    if len(codes) != 1 or not Uploads.valid_code(codes[0]):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "give one code of 6 digits (000000: no PIAA)")
    if not files:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "no files: send them in the field files")
    return codes[0], files


def _save(lock: threading.Lock, config: ApiSettings, code: str, files: Sequence[IncomingFile]) -> list[UploadResult]:
    """In a thread of its own: the memory (created if there is none yet) and the disk are synchronous."""
    with lock:
        memory = create_adapter(config.memory, TABLES)
        try:
            when = datetime.now().astimezone()
            base = LocalFileAdapter(config.base)
            results = Uploads.save(base, DbFileRepository(memory), DbUploadRepository(memory), code, files, when)
        finally:
            memory.close()
    states = Counter(r.estado for r in results)
    LOG.info(
        "upload for code %s: saved=%d existing=%d rejected=%d",
        code,
        states[UploadState.SAVED],
        states[UploadState.EXISTS],
        states[UploadState.REJECTED],
    )
    return results


@router.post(
    "/uploads",
    openapi_extra=_FORM,
    responses={
        413: {"model": Error, "description": "the body goes over the server's limit"},
        415: {"model": Error, "description": "the body isn't multipart/form-data"},
        422: {"model": Error, "description": "no files, a code that isn't 6 digits or a malformed body"},
        500: {"model": Error, "description": "a file could not be written in base/"},
        503: {"model": Error, "description": "the memory could not be opened"},
    },
)
async def upload(request: Request, config: Settings) -> list[UploadResult]:
    """Saves each file (pdf, doc or docx) in base/<anio>/<mes>/<semana>/<code>/ of the upload date, never
    overwriting, and says for each one whether it was saved, its content was already there (`ya_existe`, by sha256)
    or it was refused and why. It doesn't ingest: POST /pipeline/runs (produccion, scope new) does it next."""
    body = await request.body()
    if len(body) > config.raw_limit:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"the body goes over {config.raw_limit} bytes")
    code, files = _incoming(request.headers.get("content-type", ""), body)
    lock: threading.Lock = request.app.state.uploads
    return await run_in_threadpool(_save, lock, config, code, files)


@router.get("/uploads", responses={503: {"model": Error, "description": "the memory could not be opened"}})
def uploaded(uploads: Uploaded) -> list[Upload]:
    """The files uploaded through the API, newest first (once ingested, each `origen` is also in GET /data)."""
    return uploads.all()
