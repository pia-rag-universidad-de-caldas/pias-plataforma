"""GraphBatchClient against httpx.MockTransport: no server."""

import json
from collections.abc import Callable

import httpx
import pytest

from chunking.adapters.data import GraphBatchClient
from chunking.adapters.data.mappers import batch_body
from chunking.adapters.http import Json
from chunking.models import (
    DocumentError,
    GraphBatch,
    GraphLabel,
    GraphLink,
    GraphNode,
    GraphRelation,
    NodeKey,
    SinkError,
)

type Handler = Callable[[httpx.Request], httpx.Response]


def http(handler: Handler) -> httpx.Client:
    return httpx.Client(base_url="http://server", transport=httpx.MockTransport(handler))


def test_batch_sends_the_body() -> None:
    root, section = NodeKey(GraphLabel.JSON, "d"), NodeKey(GraphLabel.SECCION, "d:s0")
    batch = GraphBatch(
        [GraphNode(root, {"origen": "a.pdf"}), GraphNode(section, {"orden": 0})],
        [GraphLink(GraphRelation.TIENE_SECCION, root, section)],
        replace_from=root,
    )
    sent: list[Json] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert (request.method, request.url.path) == ("POST", "/data/batch")
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={"created": 2})

    GraphBatchClient(http(handler), "/data").save(batch)
    assert sent == [batch_body(batch)]
    assert sent[0]["replace_from"] == {"label": "JSON", "id": "d"}
    assert sent[0]["relationships"][0]["source"] == {"label": "JSON", "id": "d"}


def test_batch_rejected_or_missing() -> None:
    with pytest.raises(DocumentError, match="an end that doesn't exist"):
        GraphBatchClient(
            http(lambda _: httpx.Response(422, json={"detail": "an end that doesn't exist"})), "/data"
        ).save(GraphBatch([], []))
    with pytest.raises(SinkError, match="data has no /data/batch route"):
        GraphBatchClient(http(lambda _: httpx.Response(404)), "/data").save(GraphBatch([], []))
