"""ChunkingClient against httpx.MockTransport (the routes of features 043 and 045): what it asks, how it waits its
turn and how it reads the answer."""

import json
from collections.abc import Callable

import httpx
import pytest

from pipeline.adapters import ChunkingClient
from pipeline.models import NotFoundError, RejectedError

type Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler) -> httpx.Client:
    return httpx.Client(base_url="http://server", transport=httpx.MockTransport(handler))


def test_an_experiment_waits_its_turn_on_409_then_polls_until_finished() -> None:
    answers = iter(
        [
            httpx.Response(409, json={"detail": "busy"}),
            httpx.Response(202, json={"id": "e1", "status": "queued"}),
            httpx.Response(200, json={"id": "e1", "status": "running"}),
            httpx.Response(200, json={"id": "e1", "status": "finished", "error": None, "chunked": ["a"]}),
        ]
    )
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.method} {request.url.path}")
        return next(answers)

    slept: list[float] = []
    client = ChunkingClient(_client(handler), "/chunking", sleep=slept.append)
    outcome = client.experiment({"name": "x", "sha256s": ["a"], "chunking": {}})
    assert (outcome.id, outcome.status, outcome.succeeded, outcome.sha256s) == ("e1", "finished", True, ("a",))
    assert seen == ["POST /chunking/experiments"] * 2 + ["GET /chunking/experiments/e1"] * 2
    assert len(slept) == 2


def test_a_failed_experiment_is_an_outcome_that_didnt_succeed() -> None:
    answers = iter(
        [httpx.Response(202, json={"id": "e1"}), httpx.Response(200, json={"status": "failed", "error": "x"})]
    )
    outcome = ChunkingClient(_client(lambda _: next(answers)), "/chunking", sleep=lambda _: None).experiment({})
    assert (outcome.succeeded, outcome.error) == (False, "x")


def test_an_experiment_chunking_rejects_is_a_rejected_error() -> None:
    answer = httpx.Response(422, json={"detail": "max_tokens doesn't go with page"})
    client = ChunkingClient(_client(lambda _: answer), "/chunking", sleep=lambda _: None)
    with pytest.raises(RejectedError, match="doesn't go with page"):
        client.experiment({})


@pytest.mark.parametrize(("status", "succeeded"), [("finished", True), ("partial", True), ("failed", False)])
def test_promote_starts_a_run_and_reads_what_it_chunked(status: str, succeeded: bool) -> None:
    seen: list[tuple[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((f"{request.method} {request.url.path}", json.loads(request.content) if request.content else None))
        if request.method == "POST":
            return httpx.Response(202, json={"id": "r1", "status": "queued"})
        return httpx.Response(200, json={"id": "r1", "status": status, "chunked": ["a", "b"]})

    outcome = ChunkingClient(_client(handler), "/chunking", sleep=lambda _: None).promote(["a", "b"])
    assert outcome.sha256s == ("a", "b") and outcome.succeeded is succeeded
    assert seen == [
        ("POST /chunking/runs", {"sha256s": ["a", "b"], "simulate": False}),
        ("GET /chunking/runs/r1", None),
    ]


def test_apply_of_an_unknown_experiment_is_not_found() -> None:
    answer = httpx.Response(404, json={"detail": "none"})
    with pytest.raises(NotFoundError, match="e9"):
        ChunkingClient(_client(lambda _: answer), "/chunking").apply("e9")
