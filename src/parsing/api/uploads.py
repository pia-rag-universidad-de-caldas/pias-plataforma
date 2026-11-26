"""The file of POST /preview, from either body it accepts:

    application/json     {name, content (base64), mime?}
    multipart/form-data  a `file` part (its filename and Content-Type)

Multipart is read with the standard library (email): python-multipart, what FastAPI's UploadFile needs, isn't a
dependency of the project. What comes wrong is an HTTPException: 413 too large, 415 a type it doesn't preview, 422 a
body it can't read."""

import base64
import binascii
import json
from dataclasses import dataclass
from email.message import Message
from email.parser import BytesParser
from email.policy import HTTP
from typing import Annotated

from fastapi import HTTPException, Request, status
from pydantic import ConfigDict, Field, TypeAdapter, ValidationError

from parsing.config import PREVIEW_MAX_BYTES, PREVIEW_TYPES

_BASE64_OVERHEAD = 4 / 3
_FILE_PART = "file"
_JSON = "application/json"
_MULTIPART = "multipart/form-data"


@dataclass(frozen=True)
class PreviewBody:
    """The JSON body of POST /preview."""

    __pydantic_config__ = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=255)]  # its extension (or `mime`) says its type
    content: Annotated[str, Field(min_length=1)]  # the file, in base64
    mime: str | None = None


BODY = TypeAdapter(PreviewBody)
# What the OpenAPI shows (and the console's form): the JSON body; multipart, with a `file` part, too.
OPENAPI_BODY: dict[str, object] = {
    "requestBody": {
        "required": True,
        "content": {
            _JSON: {"schema": BODY.json_schema()},
            _MULTIPART: {
                "schema": {
                    "type": "object",
                    "required": [_FILE_PART],
                    "properties": {_FILE_PART: {"type": "string", "format": "binary"}},
                }
            },
        },
    }
}


@dataclass(frozen=True)
class Upload:
    name: str  # with the extension of its type: what Docling reads the format from
    content: bytes


def _too_large() -> HTTPException:
    return HTTPException(
        status.HTTP_413_CONTENT_TOO_LARGE, f"a preview reads files of up to {PREVIEW_MAX_BYTES // 2**20} MiB"
    )


def _invalid(message: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message)


def typed_name(name: str, mime: str | None) -> str:
    """`name` with the extension of a type it previews (taken from `mime` if the name has none); 415 if neither says
    one."""
    base = name.replace("\\", "/").rsplit("/", 1)[-1].strip() or "documento"
    extension = base.rsplit(".", 1)[-1].lower() if "." in base else ""
    if extension in PREVIEW_TYPES:
        return base
    wanted = (mime or "").split(";", 1)[0].strip().lower()
    for known, known_mime in PREVIEW_TYPES.items():
        if wanted == known_mime:
            return f"{base}.{known}"
    raise HTTPException(
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        f"{name!r} isn't a document it previews: {', '.join(PREVIEW_TYPES)} (by its extension or its mime)",
    )


def _from_json(raw: bytes) -> Upload:
    try:
        body = BODY.validate_python(json.loads(raw))
    except (ValueError, ValidationError) as e:
        raise _invalid(f"the body isn't {{name, content (base64), mime?}}: {str(e)[:300]}") from e
    if len(body.content) > PREVIEW_MAX_BYTES * _BASE64_OVERHEAD + 4:
        raise _too_large()
    try:
        content = base64.b64decode(body.content, validate=True)
    except (binascii.Error, ValueError) as e:
        raise _invalid("`content` isn't base64") from e
    return Upload(typed_name(body.name, body.mime), content)


def _file_part(message: Message) -> Message | None:
    for part in message.walk():
        if part.get_param("name", header="content-disposition") == _FILE_PART:
            return part
    return None


def _from_multipart(content_type: str, raw: bytes) -> Upload:
    message = BytesParser(policy=HTTP).parsebytes(b"Content-Type: " + content_type.encode() + b"\r\n\r\n" + raw)
    part = _file_part(message) if message.is_multipart() else None
    if part is None:
        raise _invalid(f"the multipart body has no `{_FILE_PART}` part")
    payload = part.get_payload(decode=True)
    content = payload if isinstance(payload, bytes) else b""
    return Upload(typed_name(part.get_filename() or "", part.get_content_type()), content)


async def read_upload(request: Request) -> Upload:
    """The file of the request, checked: not empty, not over PREVIEW_MAX_BYTES, of a type it previews."""
    content_type = request.headers.get("content-type", "")
    kind = content_type.split(";", 1)[0].strip().lower()
    if kind not in (_JSON, _MULTIPART):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"send the file as {_JSON} or {_MULTIPART}, not {kind or 'nothing'}"
        )
    raw = await request.body()
    if len(raw) > PREVIEW_MAX_BYTES * _BASE64_OVERHEAD + 64 * 1024:  # base64 or multipart's boundaries and headers
        raise _too_large()
    upload = _from_json(raw) if kind == _JSON else _from_multipart(content_type, raw)
    if not upload.content:
        raise _invalid("the file is empty")
    if len(upload.content) > PREVIEW_MAX_BYTES:
        raise _too_large()
    return upload
