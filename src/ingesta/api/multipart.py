"""A multipart/form-data body read into its parts (feature 049: POST /uploads), without python-multipart: the body is
already in memory, bounded by the server's BodyLimit, so splitting it by its boundary is enough."""

import re
from dataclasses import dataclass
from urllib.parse import unquote

_PARAM = re.compile(r';\s*([\w*.-]+)\s*=\s*("(?:[^"\\]|\\.)*"|[^;]*)')
_CRLF = b"\r\n"


class MultipartError(ValueError):
    """The body isn't a well formed multipart/form-data."""


@dataclass(frozen=True)
class Part:
    name: str  # the form field
    filename: str | None  # None in a plain field
    content: bytes


def _params(header: str) -> dict[str, str]:
    """The parameters of a header value (`form-data; name="files"; filename="a.pdf"`), unquoted; a `filename*`
    (RFC 5987, UTF-8''...) wins over `filename`."""
    found: dict[str, str] = {}
    for key, raw in _PARAM.findall(header):
        value = raw.strip()
        if value.startswith('"') and value.endswith('"') and len(value) >= 2:
            value = re.sub(r"\\(.)", r"\1", value[1:-1])
        found[key.lower()] = value
    if (extended := found.pop("filename*", None)) is not None:
        charset, _, encoded = extended.partition("''")
        found["filename"] = unquote(encoded, encoding=charset or "utf-8", errors="replace")
    return found


def boundary(content_type: str) -> str | None:
    """The boundary of a multipart/form-data Content-Type; None if it is another type or has none."""
    kind, _, _ = content_type.partition(";")
    if kind.strip().lower() != "multipart/form-data":
        return None
    return _params(content_type).get("boundary") or None


def _part(section: bytes) -> Part:
    head, separator, content = section.partition(_CRLF * 2)
    if not separator:
        raise MultipartError("a part without the blank line after its headers")
    disposition = ""
    for line in head.decode("utf-8", errors="replace").split("\r\n"):
        key, _, value = line.partition(":")
        if key.strip().lower() == "content-disposition":
            disposition = value
    params = _params(disposition)
    if "name" not in params:
        raise MultipartError("a part without Content-Disposition name")
    return Part(params["name"], params.get("filename"), content)


def parse(body: bytes, mark: str) -> list[Part]:
    """The parts of `body`, in order. MultipartError if a part is malformed or the closing boundary is missing."""
    delimiter = _CRLF + b"--" + mark.encode("latin-1")
    sections = (_CRLF + body).split(delimiter)
    parts: list[Part] = []
    for section in sections[1:]:  # the first one is the preamble
        if section.startswith(b"--"):
            return parts
        _, newline, rest = section.partition(_CRLF)  # transport padding up to the line end
        if not newline:
            raise MultipartError("a boundary that doesn't end its line")
        parts.append(_part(rest))
    raise MultipartError("the closing boundary is missing")
