"""GraphNodesClient (feature 026): the nodes of one label in data, answered as data sends them.

    GET    {data}/nodes/{label}?page&per_page
    GET    {data}/nodes/{label}/{id}[/relationships]
    DELETE {data}/nodes/{label}/{id}

One instance per label (JSON, SECCION, EXPERIMENTO...), not one class. A 404 is None (or False); another 4xx is a
DocumentError (data refused what was asked); data down is a SinkError.
"""

from collections.abc import Iterator, Mapping

import httpx

from chunking.adapters.http import BaseHttpClient, ErrorPolicy, Json, paginate, segment
from chunking.config import GRAPH_PAGE_SIZE
from chunking.models import DocumentError, GraphLabel, GraphRelation, SinkError

from .mappers import properties

DATA_ERRORS = ErrorPolicy("data", SinkError, DocumentError)


class GraphNodesClient(BaseHttpClient):
    def __init__(self, client: httpx.Client, path: str, label: GraphLabel) -> None:
        super().__init__(client, f"{path.rstrip('/')}/nodes/{label.value}", DATA_ERRORS)
        self.label = label

    def page(self, page: int, per_page: int) -> Mapping[str, Json]:
        """One page as data answers it ({nodes, total, pages...})."""
        body = self._get("", (("page", page), ("per_page", per_page)))
        if not isinstance(body, Mapping):
            raise SinkError(f"data answered an unexpected page of {self.label} nodes: {body!r}")
        return body

    def pages(self, per_page: int, first: int = 1, last: int | None = None) -> Iterator[list[Json]]:
        """The nodes of the pages `first` to `last` (or to the end), a page at a time."""
        for body in paginate(lambda page: self.page(page, per_page), "pages", SinkError, first, last):
            yield list(body.get("nodes") or [])

    def all(self) -> Iterator[Json]:
        """Every node of the label, a page of GRAPH_PAGE_SIZE at a time."""
        for body in paginate(lambda page: self.page(page, GRAPH_PAGE_SIZE), "pages", SinkError):
            yield from body.get("nodes") or []

    def get(self, id: str) -> Json:
        """The node, or None if there is none."""
        return self._get(f"/{segment(id)}")

    def properties(self, id: str) -> Mapping[str, Json] | None:
        """The properties of the node, or None if there is none."""
        return properties(self.get(id))

    def outgoing(self, id: str, type: GraphRelation) -> list[tuple[str, Mapping[str, Json]]]:
        """(target id, relationship properties) of the relationships of `type` that leave the node."""
        relationships = self._get(f"/{segment(id)}/relationships") or []
        return [
            (str(r["target"]["id"]), r.get("properties") or {})
            for r in relationships
            if isinstance(r, Mapping) and r.get("type") == type.value and r.get("source", {}).get("id") == id
        ]

    def delete(self, id: str) -> bool:
        """DETACH DELETE of the node; False if there was none."""
        return self._request("DELETE", f"/{segment(id)}") is not None
