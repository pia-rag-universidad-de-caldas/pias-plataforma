"""ParsingClient: what consultas asks of parsing for an attached document (feature 048, phase 2).

    POST {parsing}/preview {name, content (base64), mime}   → {name, pages, truncated, text, sections: [{headings, text,
                                                              pages}]}: read with the fixed configuration, never stored

Network, timeout, 5xx (Docling missing, 503; too slow, 504) or no route: ParsingDown (503); 409 (it is reading another
document) too, since trying again works; another 4xx (not a document, corrupt, too large): InvalidQuestion (422) with
parsing's reason.
"""

import base64

import httpx

from common.http import CONFLICT, BaseHttpClient, ErrorPolicy, detail
from consultas.models import InvalidQuestion, ParsingDown, PreviewedDocument

from . import mappers as to

PARSING_ERRORS = ErrorPolicy("parsing", ParsingDown, InvalidQuestion)


class ParsingClient(BaseHttpClient):
    """`path`: parsing's prefix in the server (/parsing)."""

    def __init__(self, client: httpx.Client, path: str) -> None:
        super().__init__(client, path, PARSING_ERRORS)

    def preview(self, name: str, mime: str, content: bytes) -> PreviewedDocument:
        body = {"name": name, "mime": mime, "content": base64.b64encode(content).decode("ascii")}
        response = self._send("POST", "/preview", body=body)
        if response.status_code == CONFLICT:
            raise ParsingDown(detail(response))
        if response.status_code == 404 and detail(response) == "Not Found":
            raise ParsingDown(f"it has no {self._path}/preview route (feature 048, phase 2)")
        if not response.is_success:
            raise InvalidQuestion(f"parsing can't read {name!r}: {response.status_code} {detail(response)}")
        return to.previewed(self._json(response), ParsingDown)
