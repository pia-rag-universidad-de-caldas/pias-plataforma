"""GraphNodesClient, GraphBatchClient and data's mappers (feature 026), against httpx.MockTransport: no server."""

import json
from collections.abc import Callable

import httpx
import pytest

from chunking.adapters.data import GraphBatchClient, GraphNodesClient
from chunking.adapters.data.mappers import batch_body, chunk, parameters, processed
from chunking.adapters.http import Json
from chunking.models import (
    DocumentError,
    DocumentStatus,
    GraphBatch,
    GraphLabel,
    GraphLink,
    GraphNode,
    GraphRelation,
    NodeKey,
    SinkError,
    TableMode,
)

type Handler = Callable[[httpx.Request], httpx.Response]

STORED: dict[str, Json] = {
    "origen": "2024/a.pdf",
    "sha256": "ab" * 32,
    "fingerprint": "f1",
    "estado": "fragmentado",
    "fragmentos": 3,
    "tokenizador": "sentence-transformers/all-MiniLM-L6-v2",
    "max_tokens": 512,
    "fusionar_vecinos": True,
    "repetir_encabezado_tabla": False,
    "estructura_tablas": True,
    "modo_tablas": "accurate",
    "docling": "2.134.0",
}


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


def test_processed_maps_a_json_node() -> None:
    document = processed({"id": "ab" * 32, "properties": STORED})
    assert document is not None
    assert (document.origin, document.status, document.chunks) == ("2024/a.pdf", DocumentStatus.CHUNKED, 3)
    assert document.parameters is not None and document.parameters.table_mode is TableMode.ACCURATE


@pytest.mark.parametrize(
    "node",
    [None, {"id": "x"}, {"properties": {**STORED, "origen": None}}, {"properties": {**STORED, "estado": "otro"}}],
)
def test_processed_ignores_what_chunking_did_not_write(node: Json) -> None:
    assert processed(node) is None


def test_parameters_need_every_value() -> None:
    assert parameters(STORED) is not None
    assert parameters({**STORED, "fusionar_vecinos": "yes"}) is None
    assert parameters({**STORED, "modo_tablas": "slow"}) is None


def test_chunk_with_defaults() -> None:
    mapped = chunk({"properties": {"indice": 2, "texto": "t", "paginas": [1, "x", 2], "max_tokens": True}})
    assert (mapped.index, mapped.text, mapped.pages, mapped.tokens, mapped.headings) == (2, "t", [1, 2], 0, [])
