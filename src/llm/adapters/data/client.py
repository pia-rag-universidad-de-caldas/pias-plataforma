"""DataClient: the routes of data that llm uses (its active configuration).

    GET {data}/nodes/{label}/{id}      DELETE {data}/nodes/{label}/{id}      POST {data}/batch

A 404 is None; another 4xx is DataRefused; data down (network, timeout, 5xx) is DataDown.
"""

from collections.abc import Mapping

import httpx

from common.http import BaseHttpClient, ErrorPolicy, Json, segment
from llm.models import DataDown, DataRefused, GraphBatch, GraphLabel

DATA_ERRORS = ErrorPolicy("data", DataDown, DataRefused)


def batch_body(batch: GraphBatch) -> dict[str, object]:
    """The body of POST /data/batch: never a replace_from."""
    return {
        "nodes": [
            {"label": n.key.label.value, "id": n.key.id, "properties": dict(n.properties), "mode": n.mode.value}
            for n in batch.nodes
        ],
        "relationships": [],
    }


class DataClient(BaseHttpClient):
    """`path`: data's prefix in the server (/data)."""

    def __init__(self, client: httpx.Client, path: str) -> None:
        super().__init__(client, path, DATA_ERRORS)

    def node(self, label: GraphLabel, id: str) -> Mapping[str, Json] | None:
        """The properties of the node; None if there is none."""
        found = self._get(f"/nodes/{label.value}/{segment(id)}")
        if found is None:
            return None
        properties = self._object(found, "node").get("properties")
        return properties if isinstance(properties, Mapping) else {}

    def save(self, batch: GraphBatch) -> None:
        if self._request("POST", "/batch", body=batch_body(batch)) is None:
            raise DataDown(f"data has no {self._path}/batch route")

    def delete(self, label: GraphLabel, id: str) -> bool:
        return self._request("DELETE", f"/nodes/{label.value}/{segment(id)}") is not None
