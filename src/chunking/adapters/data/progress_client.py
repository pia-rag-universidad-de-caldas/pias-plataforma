"""GraphProgressClient (feature 045): what is still to chunk with a configuration, as data counts it.

GET {data}/progress/chunking?list=missing&fingerprint&page&per_page   {sha256s, pages, ...}, ordered by sha256
"""

import httpx

from chunking.adapters.http import BaseHttpClient, Json, paginate
from chunking.config import GRAPH_PAGE_SIZE
from chunking.models import SinkError

from .mappers import texts
from .nodes_client import DATA_ERRORS


class GraphProgressClient(BaseHttpClient):
    def __init__(self, client: httpx.Client, path: str) -> None:
        super().__init__(client, f"{path.rstrip('/')}/progress/chunking", DATA_ERRORS)

    def _page(self, fingerprint: str, page: int, per_page: int) -> Json:
        body = self._get(
            "", (("list", "missing"), ("fingerprint", fingerprint), ("page", page), ("per_page", per_page))
        )
        if body is None:
            raise SinkError(f"data has no {self._path} route")
        return body

    def missing(self, fingerprint: str, page: int | None, per_page: int | None) -> list[str]:
        """One page of them, or (page None) every page."""
        size = per_page or GRAPH_PAGE_SIZE
        first, last = (page, page) if page is not None else (1, None)
        found: list[str] = []
        for body in paginate(lambda p: self._page(fingerprint, p, size), "pages", SinkError, first, last):
            found += texts(body.get("sha256s"))
        return found
