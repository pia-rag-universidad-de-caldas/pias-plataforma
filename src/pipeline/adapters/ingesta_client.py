"""IngestaClient: the routes of ingesta the selections use.

GET {ingesta}/data?page&per_page&type&year&month&week&code   one page of chunkable files
GET {ingesta}/data/file?sha256=                              one file (404: no chunkable file has it)
"""

import httpx

from pipeline.models import IngestaPort, Selection, SourcePage, UnavailableError

from .http import BaseHttpClient, QueryParams


def filter_params(selection: Selection) -> QueryParams:
    params: list[tuple[str, str | int]] = [("type", t) for t in selection.types]
    for key, value in (("year", selection.year), ("month", selection.month)):
        if value is not None:
            params.append((key, value))
    for key, text in (("week", selection.week), ("code", selection.code)):
        if text is not None:
            params.append((key, text))
    return tuple(params)


class IngestaClient(BaseHttpClient, IngestaPort):
    def __init__(self, client: httpx.Client, path: str) -> None:
        super().__init__(client, path, "ingesta")

    def page(self, selection: Selection, page: int, per_page: int) -> SourcePage:
        body = self._object(
            self._get("/data", (*filter_params(selection), ("page", page), ("per_page", per_page))), "page of /data"
        )
        try:
            files = body["archivos"]
            sha256s = tuple(str(f["sha256"]) for f in files if f.get("sha256"))
            pages = int(body["paginas"])
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            raise UnavailableError(f"ingesta answered a page of /data without archivos/paginas: {e}") from e
        reorganized = body.get("reorganizado")
        return SourcePage(sha256s, pages, None if reorganized is None else str(reorganized))

    def has(self, sha256: str) -> bool:
        return self._get("/data/file", (("sha256", sha256),)) is not None
