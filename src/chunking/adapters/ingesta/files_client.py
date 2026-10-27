"""IngestaFilesClient (feature 026): the routes of ingesta that chunking uses, answered as ingesta sends them.

    GET {ingesta}/data?page&per_page&type&year&month&week&code   one page at a time
    GET {ingesta}/data/file?sha256=                              one document (404: no chunkable file has it)
    GET {ingesta}/data/content?origin=                           its bytes (404: not registered or not chunkable)

Any 4xx of /data, and a 422 anywhere, mean chunking asked wrong: SourceError, the run stops. A 404 of one file is a
DocumentError: only that document fails.
"""

from collections.abc import Iterator, Mapping

import httpx

from chunking.adapters.http import BaseHttpClient, ErrorPolicy, Json, paginate
from chunking.models import DocumentError, DocumentFilter, SourceError

from .mappers import filter_params


class IngestaFilesClient(BaseHttpClient):
    def __init__(self, client: httpx.Client, path: str) -> None:
        super().__init__(client, path, ErrorPolicy("ingesta", SourceError, SourceError))

    def page(self, filter: DocumentFilter, page: int, per_page: int) -> Json:
        return self._get("/data", (*filter_params(filter), ("page", page), ("per_page", per_page)), SourceError)

    def pages(
        self, filter: DocumentFilter, per_page: int, first: int = 1, last: int | None = None
    ) -> Iterator[Mapping[str, Json]]:
        """The pages `first` to `last` (default: every page) of GET /data as ingesta answers them ({archivos, paginas,
        reorganizado...}), one at a time."""
        return paginate(lambda page: self.page(filter, page, per_page), "paginas", SourceError, first, last)

    def file(self, sha256: str) -> Json:
        return self._get("/data/file", (("sha256", sha256),), DocumentError)

    def content(self, origin: str) -> bytes:
        response = self._request("GET", "/data/content", (("origin", origin),), not_found=DocumentError)
        assert response is not None  # a 404 raised DocumentError
        return response.content
