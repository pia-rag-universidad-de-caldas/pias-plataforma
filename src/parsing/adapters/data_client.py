"""DataClient: the routes of data that parsing uses (data is the storage of every module, feature 042).

    GET  {data}/nodes/{label}?omit=...&page&per_page
    GET  {data}/nodes/{label}/{id}[?omit=...]
    POST {data}/batch

A 404 is None; another 4xx is a DocumentError (data refused it); data down is a SinkError.
"""

from collections.abc import Iterator, Mapping, Sequence

import httpx

from common.http import BaseHttpClient, ErrorPolicy, Json, paginate, segment
from parsing.models import DocumentError, GraphBatch, GraphLabel, NodeKey, SinkError

DATA_ERRORS = ErrorPolicy("data", SinkError, DocumentError)


def _key(key: NodeKey) -> dict[str, str]:
    return {"label": key.label.value, "id": key.id}


def batch_body(batch: GraphBatch) -> dict[str, object]:
    """The body of POST /data/batch."""
    return {
        "replace_from": _key(batch.replace_from) if batch.replace_from else None,
        "nodes": [{**_key(n.key), "properties": dict(n.properties), "mode": n.mode.value} for n in batch.nodes],
        "relationships": [
            {"type": r.type.value, "source": _key(r.source), "target": _key(r.target), "properties": {}}
            for r in batch.links
        ],
    }


def properties(node: Json) -> Mapping[str, Json] | None:
    """The properties of a node as data answers it ({label, id, properties}); None if it isn't one."""
    if not isinstance(node, Mapping):
        return None
    found = node.get("properties")
    return found if isinstance(found, Mapping) else {}


def _omit(omit: Sequence[str]) -> tuple[tuple[str, str | int], ...]:
    return tuple(("omit", name) for name in omit)


class DataClient(BaseHttpClient):
    """`path`: data's prefix in the server (/data)."""

    def __init__(self, client: httpx.Client, path: str) -> None:
        super().__init__(client, path, DATA_ERRORS)

    def node(self, label: GraphLabel, id: str, omit: Sequence[str] = ()) -> Mapping[str, Json] | None:
        """The properties of the node; None if there is none."""
        found = self._get(f"/nodes/{label.value}/{segment(id)}", _omit(omit) or None)
        return None if found is None else properties(found)

    def nodes(
        self, label: GraphLabel, per_page: int, omit: Sequence[str] = ()
    ) -> Iterator[tuple[str, Mapping[str, Json]]]:
        """(id, properties) of every node of the label, a page at a time."""

        def page(number: int) -> Json:
            return self._get(f"/nodes/{label.value}", (*_omit(omit), ("page", number), ("per_page", per_page)))

        for body in paginate(page, "pages", SinkError):
            for node in body.get("nodes") or []:
                found = properties(node)
                if found is not None and isinstance(node, Mapping) and "id" in node:
                    yield str(node["id"]), found

    def save(self, batch: GraphBatch) -> None:
        if self._request("POST", "/batch", body=batch_body(batch)) is None:
            raise SinkError(f"data has no {self._path}/batch route")
