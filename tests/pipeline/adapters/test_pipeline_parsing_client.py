"""ParsingClient against httpx.MockTransport (feature 042's routes): only sha256s go, never a file."""

import json
from collections.abc import Callable

import httpx

from pipeline.adapters import ParsingClient

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
