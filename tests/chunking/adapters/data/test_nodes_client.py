"""GraphNodesClient against httpx.MockTransport: no server."""

from collections.abc import Callable

import httpx
import pytest

from chunking.adapters.data import GraphNodesClient
from chunking.models import (
    DocumentError,
    GraphLabel,
    GraphRelation,
    SinkError,
)

type Handler = Callable[[httpx.Request], httpx.Response]


def http(handler: Handler) -> httpx.Client:
    return httpx.Client(base_url="http://server", transport=httpx.MockTransport(handler))


def nodes(handler: Handler, label: GraphLabel = GraphLabel.JSON) -> GraphNodesClient:
    return GraphNodesClient(http(handler), "/data", label)


def test_get_escapes_the_id_and_404_is_none() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.raw_path.decode())
        return httpx.Response(404, json={"detail": "no node"})

    assert nodes(handler, GraphLabel.SECCION).get("abc:s/1") is None
    assert paths == ["/data/nodes/SECCION/abc%3As%2F1"]


def test_properties_of_a_node() -> None:
    client = nodes(lambda _: httpx.Response(200, json={"label": "JSON", "id": "x", "properties": {"a": 1}}))
    assert client.properties("x") == {"a": 1}


def test_all_walks_every_page() -> None:
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.params["page"])
        page = int(request.url.params["page"])
        return httpx.Response(200, json={"nodes": [{"id": f"n{page}"}], "total": 2, "pages": 2})

    assert [n["id"] for n in nodes(handler).all()] == ["n1", "n2"]
    assert asked == ["1", "2"]


def test_an_unexpected_page_is_a_sink_error() -> None:
    with pytest.raises(SinkError, match="unexpected page of JSON nodes"):
        nodes(lambda _: httpx.Response(200, json=[1, 2])).page(1, 10)


def test_outgoing_keeps_only_that_type_leaving_the_node() -> None:
    relationships = [
        {"type": "TIENE_SECCION", "source": {"id": "d"}, "target": {"id": "d:s0"}, "properties": {"k": 1}},
        {"type": "TIENE_SECCION", "source": {"id": "other"}, "target": {"id": "d"}, "properties": {}},
        {"type": "ES", "source": {"id": "d"}, "target": {"id": "p"}, "properties": {}},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/data/nodes/JSON/d/relationships"
        return httpx.Response(200, json=relationships)

    assert nodes(handler).outgoing("d", GraphRelation.TIENE_SECCION) == [("d:s0", {"k": 1})]


def test_delete_is_false_when_there_was_none() -> None:
    assert nodes(lambda r: httpx.Response(204 if r.method == "DELETE" else 500)).delete("x") is True
    assert nodes(lambda _: httpx.Response(404, json={"detail": "no node"})).delete("x") is False


def test_data_refused_or_down() -> None:
    with pytest.raises(DocumentError, match="data rejected GET /data/nodes/JSON/x: 422"):
        nodes(lambda _: httpx.Response(422, json={"detail": "bad label"})).get("x")
    with pytest.raises(SinkError, match="503 Neo4j"):
        nodes(lambda _: httpx.Response(503, json={"detail": "Neo4j doesn't answer"})).get("x")
