"""The pipeline's HTTP clients (feature 028) against httpx.MockTransport: what they ask and how they read it."""

import json
from collections.abc import Callable

import httpx
import pytest

from pipeline.adapters import ChunkingClient, GraphRunStore, IngestaClient
from pipeline.domain import PIAA, Engine
from pipeline.models import (
    FILE_BATCH,
    ActionOutput,
    RejectedError,
    RunRequest,
    Selection,
    UnavailableError,
)

type Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler) -> httpx.Client:
    return httpx.Client(base_url="http://server", transport=httpx.MockTransport(handler))


def test_chunking_waits_its_turn_on_409_then_polls_until_finished() -> None:
    answers = iter(
        [
            httpx.Response(409, json={"detail": "busy"}),
            httpx.Response(202, json={"id": "e1", "status": "running"}),
            httpx.Response(200, json={"id": "e1", "status": "running"}),
            httpx.Response(200, json={"id": "e1", "status": "finished", "error": None}),
        ]
    )
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.method} {request.url.path}")
        return next(answers)

    slept: list[float] = []
    client = ChunkingClient(_client(handler), "/chunking", sleep=slept.append)
    outcome = client.run_experiment({"name": "x", "files": {"sha256s": ["a"]}})
    assert (outcome.id, outcome.status) == ("e1", "finished")
    assert seen == ["POST /chunking/experiments"] * 2 + ["GET /chunking/experiments/e1"] * 2
    assert len(slept) == 2


def test_chunking_rejects_and_promotes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/promote"):
            body = {"experiment": "e1", "kind": "conversion", "promoted": 3, "failed": [{"sha256": "b", "error": "x"}]}
            return httpx.Response(200, json=body)
        return httpx.Response(422, json={"detail": "files.pages requires per_page"})

    client = ChunkingClient(_client(handler), "/chunking", sleep=lambda _: None)
    with pytest.raises(RejectedError, match="requires per_page"):
        client.run_experiment({})
    promotion = client.promote("e1")
    assert (promotion.count, promotion.promoted, promotion.failed) == (3, None, (("b", "x"),))


def test_ingesta_page_sends_the_filters_and_reads_the_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get_list("type") == ["pdf", "docx"]
        assert request.url.params["year"] == "2024" and request.url.params["per_page"] == "20"
        body = {"reorganizado": "t", "paginas": 4, "archivos": [{"sha256": "a"}, {"sha256": "b"}]}
        return httpx.Response(200, json=body)

    page = IngestaClient(_client(handler), "/ingesta").page(
        Selection(all=True, types=("pdf", "docx"), year=2024), 2, 20
    )
    assert (page.sha256s, page.pages, page.reorganized) == (("a", "b"), 4, "t")


def test_ingesta_down_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detalle": "memory"})

    with pytest.raises(UnavailableError, match="memory"):
        IngestaClient(_client(handler), "/ingesta").has("a")


def test_the_store_writes_a_run_in_one_batch_and_reads_it_back() -> None:
    nodes: dict[tuple[str, str], dict[str, object]] = {}
    links: set[tuple[str, str]] = set()

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/data/batch":
            body = json.loads(request.content)
            links.update((r["type"], r["target"]["id"]) for r in body.get("relationships", []))
            for node in body["nodes"]:
                nodes[(node["label"], node["id"])] = node["properties"]
            return httpx.Response(200, json={})
        _, _, _, label, id = path.split("/")
        found = nodes.get((label, id))
        if found is None:
            return httpx.Response(404, json={"detail": "none"})
        return httpx.Response(200, json={"label": label, "id": id, "properties": found})

    store = GraphRunStore(_client(handler), "/data")
    run = Engine.start(Engine.new("r1", RunRequest("piaa", "n", Selection(all=True), {}), PIAA, "t0"), "t0")
    run = Engine.done(run, ActionOutput({FILE_BATCH: ["a"]}), "t1")  # enters the conversion cycle
    run = Engine.done(run, ActionOutput({"conversion": "e1"}, None, "e1"), "t2")
    store.save_run(run, created=True)
    assert (
        ("PIPE_DE", "piaa") in links
        and ("PIPE_USA", "e1") in links
        and ("PIPE_TIENE_ITERACION", "r1:conversion:1") in links
    )
    assert store.run("r1") == run
    assert store.run("nope") is None
