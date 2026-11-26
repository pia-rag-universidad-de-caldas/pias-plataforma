"""ParsingClient against httpx.MockTransport (feature 042's routes): only sha256s go, never a file."""

import json
from collections.abc import Callable

import httpx
import pytest

from pipeline.adapters import ParsingClient
from pipeline.models import ActionError, JobWatch

type Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler) -> httpx.Client:
    return httpx.Client(base_url="http://server", transport=httpx.MockTransport(handler))


def test_a_run_without_sha256s_sends_none() -> None:
    bodies: list[object] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            bodies.append(json.loads(request.content))
            return httpx.Response(202, json={"id": "p1", "status": "queued"})
        return httpx.Response(200, json={"id": "p1", "status": "done", "parsed": ["a"]})

    outcome = ParsingClient(_client(handler), "/parsing", sleep=lambda _: None).parse([])
    assert bodies == [{"redo": False, "simulate": False}] and outcome.sha256s == ("a",)


def test_a_parsing_run_waits_its_turn_and_reads_what_it_parsed() -> None:
    answers = iter(
        [
            httpx.Response(409, json={"detail": "the line is full"}),
            httpx.Response(202, json={"id": "p1", "status": "queued"}),
            httpx.Response(200, json={"id": "p1", "status": "done", "parsed": ["a"]}),
        ]
    )
    bodies: list[object] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            bodies.append(json.loads(request.content))
        return next(answers)

    outcome = ParsingClient(_client(handler), "/parsing", sleep=lambda _: None).parse(["a", "b"])
    assert (outcome.succeeded, outcome.sha256s) == (True, ("a",))
    assert bodies[-1] == {"sha256s": ["a", "b"], "redo": False, "simulate": False}


def test_a_cancelled_run_starts_no_parsing() -> None:
    sent: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request.url.path)
        return httpx.Response(202, json={"id": "p1", "status": "queued"})

    watch = JobWatch()
    watch.cancel()
    with pytest.raises(ActionError, match="cancelled"):
        ParsingClient(_client(handler), "/parsing", sleep=lambda _: None).parse(["a"], watch)
    assert sent == []


def test_cancelling_asks_parsing_to_stop_the_run_it_waits_for() -> None:
    sent: list[str] = []
    watch = JobWatch()

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(f"{request.method} {request.url.path}")
        if request.url.path.endswith("/cancel"):
            return httpx.Response(200, json={"id": "p1", "status": "running", "cancel_requested": True})
        if request.method == "POST":
            return httpx.Response(202, json={"id": "p1", "status": "queued"})
        if not watch.cancelled:
            watch.cancel()  # the pipeline run is cancelled while parsing runs
            return httpx.Response(200, json={"id": "p1", "status": "running"})
        return httpx.Response(200, json={"id": "p1", "status": "cancelled", "parsed": ["a"]})

    outcome = ParsingClient(_client(handler), "/parsing", sleep=lambda _: None).parse(["a", "b"], watch)
    assert "POST /parsing/runs/p1/cancel" in sent and not outcome.succeeded and outcome.sha256s == ("a",)
