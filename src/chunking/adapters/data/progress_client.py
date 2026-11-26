"""GraphProgressClient (features 045 and 059): what is still to chunk with a configuration, and every parsed JSON, as
data counts them.

GET {data}/progress/chunking?list=missing|all&fingerprint&page&per_page   {sha256s, pages, total...}, by sha256
"""

from collections.abc import Mapping
from typing import Literal

import httpx

from chunking.adapters.http import BaseHttpClient, Json, QueryParams, paginate
from chunking.config import GRAPH_PAGE_SIZE
from chunking.models import SinkError

from .mappers import integer, texts
from .nodes_client import DATA_ERRORS

type Listing = Literal["missing", "all"]


class GraphProgressClient(BaseHttpClient):
    def __init__(self, client: httpx.Client, path: str) -> None:
        super().__init__(client, f"{path.rstrip('/')}/progress/chunking", DATA_ERRORS)

    def _page(self, listed: Listing, fingerprint: str | None, page: int, per_page: int) -> Json:
        query: QueryParams = (("list", listed), ("page", page), ("per_page", per_page))
        if fingerprint is not None:
            query = (*query, ("fingerprint", fingerprint))
        body = self._get("", query)
        if body is None:
            raise SinkError(f"data has no {self._path} route")
        return body

    def _listed(self, listed: Listing, fingerprint: str | None, page: int | None, per_page: int | None) -> list[str]:
        size = per_page or GRAPH_PAGE_SIZE
        first, last = (page, page) if page is not None else (1, None)
        found: list[str] = []
        for body in paginate(lambda p: self._page(listed, fingerprint, p, size), "pages", SinkError, first, last):
            found += texts(body.get("sha256s"))
        return found

    def missing(self, fingerprint: str, page: int | None, per_page: int | None) -> list[str]:
        """One page of them, or (page None) every page."""
        return self._listed("missing", fingerprint, page, per_page)

    def parsed(self) -> list[str]:
        """Every parsed JSON (feature 059), a page of GRAPH_PAGE_SIZE at a time."""
        return self._listed("all", None, None, None)

    def parsed_count(self) -> int:
        """How many parsed JSON there are: the total of a page of one."""
        body = self._page("all", None, 1, 1)
        total = integer(body.get("total")) if isinstance(body, Mapping) else None
        if total is None:
            raise SinkError(f"data answered an unexpected page of {self._path}: {body!r}")
        return total
