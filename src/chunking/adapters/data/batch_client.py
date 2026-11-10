"""GraphBatchClient (feature 026): POST {data}/batch, nodes and relationships written all or nothing."""

import httpx

from chunking.adapters.http import BaseHttpClient
from chunking.models import GraphBatch, SinkError

from .mappers import batch_body
from .nodes_client import DATA_ERRORS


class GraphBatchClient(BaseHttpClient):
    def __init__(self, client: httpx.Client, path: str) -> None:
        super().__init__(client, path, DATA_ERRORS)

    def save(self, batch: GraphBatch) -> None:
        """A 4xx (outside the schema, a missing end...) is a DocumentError: nothing was written."""
        if self._request("POST", "/batch", body=batch_body(batch)) is None:
            raise SinkError(f"data has no {self._path}/batch route")
