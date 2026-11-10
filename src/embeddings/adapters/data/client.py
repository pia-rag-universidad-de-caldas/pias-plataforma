"""DataClient: the routes of data that embeddings uses.

    GET    {data}/nodes/{label}?page&per_page            GET {data}/nodes/{label}/{id}[?omit=...]
    GET    {data}/nodes/{label}/{id}/relationships       DELETE {data}/nodes/{label}/{id}
    POST   {data}/batch                                  (the vectors, with merge; the records)
    PUT    {data}/vectors/indexes/{name}              DELETE {data}/vectors/indexes/{name}?drop_property=true

A 404 is None; another 4xx is a DocumentError (data refused it); data down (network, timeout, 5xx) is UpstreamDown.
"""

from collections.abc import Iterator, Mapping, Sequence

import httpx

from common.http import BaseHttpClient, ErrorPolicy, Json, QueryParams, paginate, segment
from embeddings.config import MAX_PER_PAGE
from embeddings.models import (
    DocumentError,
    GraphBatch,
    GraphLabel,
    GraphRelation,
    NodeKey,
    UpstreamDown,
    VectorIndexSpec,
)

DATA_ERRORS = ErrorPolicy("data", UpstreamDown, DocumentError)


def _key(key: NodeKey) -> dict[str, str]:
    return {"label": key.label.value, "id": key.id}


def batch_body(batch: GraphBatch) -> dict[str, object]:
    """The body of POST /data/batch; a replace_from only when the batch has one (deleting an experiment's vectors)."""
    body: dict[str, object] = {
        "nodes": [{**_key(n.key), "properties": dict(n.properties), "mode": n.mode.value} for n in batch.nodes],
        "relationships": [
            {"type": r.type.value, "source": _key(r.source), "target": _key(r.target), "properties": {}}
            for r in batch.links
        ],
    }
    if batch.replace_from is not None:
        body["replace_from"] = _key(batch.replace_from)
    return body


def properties(node: Json) -> Mapping[str, Json] | None:
    """The properties of a node as data answers it ({label, id, properties}); None if it isn't one."""
    if not isinstance(node, Mapping):
        return None
    found = node.get("properties")
    return found if isinstance(found, Mapping) else {}


def _omit(omit: Sequence[str]) -> QueryParams | None:
    return tuple(("omit", name) for name in omit) or None


class DataClient(BaseHttpClient):
    """`path`: data's prefix in the server (/data)."""

    def __init__(self, client: httpx.Client, path: str) -> None:
        super().__init__(client, path, DATA_ERRORS)

    def node(self, label: GraphLabel, id: str, omit: Sequence[str] = ()) -> Mapping[str, Json] | None:
        """The properties of the node; None if there is none."""
        return properties(self._get(f"/nodes/{label.value}/{segment(id)}", _omit(omit)))

    def nodes(self, label: GraphLabel, omit: Sequence[str] = ()) -> Iterator[tuple[str, Mapping[str, Json]]]:
        """(id, properties) of every node of the label, a page at a time."""

        def page(number: int) -> Json:
            pages = (("page", number), ("per_page", MAX_PER_PAGE))
            return self._get(f"/nodes/{label.value}", pages + tuple(("omit", name) for name in omit))

        for body in paginate(page, "pages", UpstreamDown):
            for node in body.get("nodes") or []:
                found = properties(node)
                if found is not None and "id" in node:
                    yield str(node["id"]), found

    def outgoing(self, label: GraphLabel, id: str, type: GraphRelation) -> list[str]:
        """The ids of the nodes the relationships of `type` that leave the node go to; [] if there is no node."""
        found = self._get(f"/nodes/{label.value}/{segment(id)}/relationships") or []
        return [
            str(r["target"]["id"])
            for r in found
            if isinstance(r, Mapping)
            and r.get("type") == type.value
            and isinstance(r.get("source"), Mapping)
            and r["source"].get("label") == label.value
            and r["source"].get("id") == id
            and isinstance(r.get("target"), Mapping)
        ]

    def save(self, batch: GraphBatch) -> None:
        """All of it or nothing; a 4xx (outside the schema, a missing end...) is a DocumentError."""
        if self._request("POST", "/batch", body=batch_body(batch)) is None:
            raise UpstreamDown(f"data has no {self._path}/batch route")

    def delete(self, label: GraphLabel, id: str) -> bool:
        return self._request("DELETE", f"/nodes/{label.value}/{segment(id)}") is not None

    def ensure_index(self, index: VectorIndexSpec) -> None:
        """Any refusal is the machine's, not a document's: a 409 (an index with that name and another definition) or
        a 422 would make every document fail the same way."""
        route = f"/vectors/indexes/{segment(index.name)}"
        body = {"label": index.label, "property": index.property, "dimensions": index.dimensions}
        response = self._send("PUT", route, body=body)
        if not response.is_success:
            raise UpstreamDown(str(self._rejected("PUT", route, response)))

    def drop_index(self, name: str, drop_property: bool) -> bool:
        """False if data has no index with that name."""
        route = f"/vectors/indexes/{segment(name)}"
        return self._request("DELETE", route, (("drop_property", str(drop_property).lower()),)) is not None
