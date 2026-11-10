"""POST /preview (feature 048, phase 2): a document read with the fixed configuration and given back as text, without
writing anything in data. consultas uses it to search what is similar to a document attached to a question; it never
enters the corpus (that is the upload, feature 049)."""

from fastapi import APIRouter, HTTPException, Request, status

from common.api import Error
from parsing.adapters.docling_parser import MISSING
from parsing.api.dependencies import DocumentParser, Previews
from parsing.api.preview_slot import PreviewBusy, PreviewTimeout
from parsing.api.uploads import OPENAPI_BODY, read_upload
from parsing.config import PREVIEW_MAX_BYTES, PREVIEW_MAX_PAGES, PREVIEW_TIMEOUT
from parsing.domain import preview
from parsing.models import ParseError, ParserUnavailable, PreviewDocument

router = APIRouter(tags=["preview"])


@router.post(
    "/preview",
    openapi_extra=OPENAPI_BODY,
    responses={
        409: {"model": Error, "description": "another document is being previewed"},
        413: {"model": Error, "description": f"a file over {PREVIEW_MAX_BYTES // 2**20} MiB"},
        415: {"model": Error, "description": "not a pdf, docx or doc (by its extension or its mime)"},
        422: {"model": Error, "description": "a body it can't read, an empty file, or one Docling can't convert"},
        503: {"model": Error, "description": "Docling is not installed, or its models don't load"},
        504: {"model": Error, "description": f"it took more than {PREVIEW_TIMEOUT:.0f} s"},
    },
)
async def preview_document(request: Request, parser: DocumentParser, previews: Previews) -> PreviewDocument:
    """Parses a pdf, docx or doc with the same fixed configuration as the runs (GET /config) and answers its text, cut
    in sections by its titles. **Nothing is stored**: the document doesn't enter the corpus nor data (to add one to
    the corpus, the upload of feature 049). Of a PDF only the first pages are read (`truncated` says so); one preview
    at a time, synchronous, with a time limit. The body is JSON `{name, content (base64), mime?}` or multipart with a
    `file` part."""
    upload = await read_upload(request)
    if not parser.available():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, MISSING)

    def read() -> PreviewDocument:
        output = parser.preview(upload.name, upload.content, PREVIEW_MAX_PAGES)
        return preview(upload.name, output.document, output.coverage, PREVIEW_MAX_PAGES)

    try:
        return await previews.run(read, PREVIEW_TIMEOUT)
    except PreviewBusy as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except PreviewTimeout as e:
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, str(e)) from e
    except ParseError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Docling can't read it: {e}") from e
    except ParserUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e
