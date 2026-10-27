"""DataClient: the official JSON nodes, for the selections of JSON.

GET {data}/nodes/JSON?page&per_page
"""

import httpx

from pipeline.models import DataPort, IdPage, UnavailableError

from .http import BaseHttpClient

JSON_LABEL = "JSON"


class DataClient(BaseHttpClient, DataPort):
    def __init__(self, client: httpx.Client, path: str) -> None:
        super().__init__(client, f"{path.rstrip('/')}/nodes/{JSON_LABEL}", "data")

    def json_page(self, page: int, per_page: int) -> IdPage:
        body = self._object(self._get("", (("page", page), ("per_page", per_page))), "page of JSON nodes")
        try:
            return IdPage(tuple(str(n["id"]) for n in body["nodes"]), int(body["pages"]))
        except (KeyError, TypeError, ValueError) as e:
            raise UnavailableError(f"data answered a page of JSON nodes without nodes/pages: {e}") from e
