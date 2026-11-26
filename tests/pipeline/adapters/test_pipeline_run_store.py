"""GraphRunStore against httpx.MockTransport: a run written in one batch and read back."""

import json
from collections.abc import Callable

import httpx

from pipeline.adapters import GraphRunStore
from pipeline.domain import LABORATORY, PRODUCTION, Engine
from pipeline.models import (
    CHUNKING_EXPERIMENT,
    EMBEDDINGS_EXPERIMENT,
    FILE_BATCH,
    PARSED,
    RAW_FILES,
    ActionOutput,
    Decision,
    DecisionKind,
    JsonObject,
    RunRequest,
    RunStatus,
    Selection,
)

type Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler) -> httpx.Client:
    return httpx.Client(base_url="http://server", transport=httpx.MockTransport(handler))


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
    request = RunRequest("laboratorio", "n", Selection(all=True), {})
    run = Engine.start(Engine.new("r1", request, LABORATORY, "t0"), "t0")
    run = Engine.done(run, ActionOutput({FILE_BATCH: ["a"]}), "t1")
    run = Engine.done(run, ActionOutput({PARSED: ["a"]}), "t1")  # enters the laboratory cycle
    run = Engine.done(run, ActionOutput({CHUNKING_EXPERIMENT: "c1"}, None, "c1"), "t2")
    run = Engine.done(run, ActionOutput({EMBEDDINGS_EXPERIMENT: "e1"}, None, embeddings_experiment="e1"), "t2")
    score: JsonObject = {"score": 4, "criteria": {"coherencia": 4}, "author": "lab", "comment": "bien"}
    run = Engine.decide(Engine.wait(run, "t3"), Decision(DecisionKind.RETRY, score=score), "laboratorio", "t3")
    store.save_run(run, created=True)
    assert ("PIPE_DE", "laboratorio") in links and ("PIPE_USA", "c1") in links
    assert ("PIPE_USA", "e1") in links  # the embeddings experiment too (EXP_EMBEDDINGS, feature 046)
    iteration = nodes[("PIPE_ITERACION", "r1:laboratorio:1")]
    assert iteration["experimentos"] == ["c1"] and iteration["experimentos_embeddings"] == ["e1"]
    assert (iteration["puntuacion"], iteration["autor"], iteration["comentario"]) == (4.0, "lab", "bien")
    assert json.loads(str(iteration["criterios"])) == {"coherencia": 4}
    assert store.run("r1") == run
    assert store.run("nope") is None


def test_the_iteration_keeps_its_llm_and_what_it_reuses() -> None:
    nodes: dict[tuple[str, str], dict[str, object]] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/data/batch":
            for node in json.loads(request.content)["nodes"]:
                nodes[(node["label"], node["id"])] = node["properties"]
            return httpx.Response(200, json={})
        _, _, _, label, id = request.url.path.split("/")
        found = nodes.get((label, id))
        if found is None:
            return httpx.Response(404, json={"detail": "none"})
        return httpx.Response(200, json={"label": label, "id": id, "properties": found})

    store = GraphRunStore(_client(handler), "/data")
    llm: JsonObject = {"model": "qwen", "temperature": 0.2}
    request = RunRequest("laboratorio", "n", Selection(all=True), {"laboratorio": {"llm": llm}})
    run = Engine.start(Engine.new("r1", request, LABORATORY, "t0"), "t0")
    run = Engine.done(run, ActionOutput({FILE_BATCH: ["a"]}), "t1")
    run = Engine.done(run, ActionOutput({PARSED: ["a"]}), "t1")
    run = Engine.done(run, ActionOutput({CHUNKING_EXPERIMENT: "c1"}, None, "c1"), "t2")
    run = Engine.done(run, ActionOutput({EMBEDDINGS_EXPERIMENT: "e1"}, None, embeddings_experiment="e1"), "t2")
    retry = Decision(DecisionKind.RETRY, next={"llm": {"temperature": 0.9}})
    run = Engine.wait(Engine.decide(Engine.wait(run, "t3"), retry, "laboratorio", "t3"), "t3")
    store.save_run(run, created=True)
    first, second = nodes[("PIPE_ITERACION", "r1:laboratorio:1")], nodes[("PIPE_ITERACION", "r1:laboratorio:2")]
    assert json.loads(str(first["config_llm"])) == llm and "reutiliza" not in first
    assert json.loads(str(second["config_llm"])) == {"model": "qwen", "temperature": 0.9}
    assert second["reutiliza"] == 1 and second["experimentos"] == ["c1"]
    assert store.run("r1") == run


def test_runs_by_status_use_the_indexed_data_route_and_actor_filter() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/data/pipeline/runs"
        assert request.url.params["status"] == "waiting"
        assert request.url.params["actor"] == "lab"
        assert request.url.params["page"] == "1"
        return httpx.Response(200, json={"page": 1, "per_page": 500, "total": 0, "pages": 0, "nodes": []})

    store = GraphRunStore(_client(handler), "/data")

    assert store.runs_by_status(RunStatus.WAITING, "lab") == []


def test_the_run_keeps_its_parts_and_their_size() -> None:
    nodes: dict[tuple[str, str], dict[str, object]] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/data/batch":
            for node in json.loads(request.content)["nodes"]:
                nodes[(node["label"], node["id"])] = node["properties"]
            return httpx.Response(200, json={})
        _, _, _, label, id = request.url.path.split("/")
        found = nodes.get((label, id))
        if found is None:
            return httpx.Response(404, json={"detail": "none"})
        return httpx.Response(200, json={"label": label, "id": id, "properties": found})

    store = GraphRunStore(_client(handler), "/data")
    run = Engine.start(Engine.new("r1", RunRequest("produccion", "n", None, {}, 1), PRODUCTION, "t0"), "t0")
    run = Engine.done(run, ActionOutput({RAW_FILES: "i1"}), "t1")
    run = Engine.done(run, ActionOutput({FILE_BATCH: ["a", "b"]}), "t1")  # the internal task that freezes the batch
    run = Engine.done(run, ActionOutput({PARSED: ["a"]}), "t2")
    store.save_run(run, created=True)
    stored = nodes[("PIPE_CORRIDA", "r1")]
    assert stored["tamano_parte"] == 1 and len(json.loads(str(stored["partes"]))) == 2
    assert store.run("r1") == run
