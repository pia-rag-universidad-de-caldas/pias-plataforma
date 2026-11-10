"""GET /processes and its WebSocket (feature 039) over any source: the same board, and only what applies."""

from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from common.api import process_router
from common.processes import ProcessFacts, ProcessSnapshot, ProcessState, describe

STARTED = "2026-11-06T10:00:00+00:00"


class Source:
    def __init__(self) -> None:
        self.facts = [
            ProcessFacts("a", "chunking", "experiment", "one", ProcessState.RUNNING, STARTED, STARTED, phase="01"),
            ProcessFacts("b", "chunking", "experiment", "two", ProcessState.QUEUED, STARTED, phase="02", position=1),
            ProcessFacts("c", "ingesta", "ingestion", "x", ProcessState.FINISHED, STARTED, STARTED, STARTED),
        ]

    def snapshot(self, at: datetime) -> ProcessSnapshot:
        return ProcessSnapshot(tuple(describe(f, at) for f in self.facts))


def client(source: Source) -> TestClient:
    app = FastAPI()
    app.include_router(process_router(lambda _: [source]))
    return TestClient(app)


def test_get_counts_and_leaves_out_what_does_not_apply() -> None:
    body = client(Source()).get("/processes").json()
    assert body["counts"]["queued"] == 1 and body["counts"]["running"] == 1
    ended = next(p for p in body["processes"] if p["id"] == "c")
    assert set(ended) == {"id", "module", "kind", "name", "state", "started", "finished", "duration_seconds"}


def test_get_filters_by_phase_and_state() -> None:
    api = client(Source())
    assert [p["id"] for p in api.get("/processes", params={"phase": "02"}).json()["processes"]] == ["b"]
    found = api.get("/processes", params=[("state", "running"), ("state", "finished")]).json()["processes"]
    assert [p["id"] for p in found] == ["a", "c"]


def test_the_socket_sends_the_board_at_once_with_the_same_filters() -> None:
    with client(Source()).websocket_connect("/processes/ws?phase=01") as socket:
        body = socket.receive_json()
    assert [p["id"] for p in body["processes"]] == ["a"]


def test_the_socket_sends_it_again_when_it_changes() -> None:
    source = Source()
    source.facts = source.facts[1:2]
    with client(source).websocket_connect("/processes/ws") as socket:
        assert socket.receive_json()["counts"]["finished"] == 0
        source.facts = [ProcessFacts("c", "m", "k", "n", ProcessState.FINISHED, STARTED, STARTED, STARTED)]
        assert socket.receive_json()["counts"]["finished"] == 1


def test_the_socket_refuses_another_site() -> None:
    with (
        pytest.raises(WebSocketDisconnect),
        client(Source()).websocket_connect("/processes/ws", headers={"Origin": "http://evil.example"}),
    ):
        pass


def test_the_socket_accepts_its_own_origin() -> None:
    headers = {"Origin": "http://testserver"}
    with client(Source()).websocket_connect("/processes/ws", headers=headers) as socket:
        assert socket.receive_json()["counts"]["running"] == 1


def test_the_socket_accepts_a_client_without_origin() -> None:
    with client(Source()).websocket_connect("/processes/ws") as socket:
        assert socket.receive_json()["counts"]["running"] == 1
