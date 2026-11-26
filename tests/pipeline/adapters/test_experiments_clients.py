"""The routes of the experiments pipeline (feature 062) against httpx.MockTransport: data's selection and the
EXPERIMENTO it waits on, chunking's experiments (start, info, documents, resume, active config) and embeddings'
experiments of a chunking experiment, their resume and an official run with another model."""

import json
from collections.abc import Callable

import httpx
import pytest

from pipeline.adapters import ChunkingClient, DataClient, EmbeddingsClient
from pipeline.models import (
    ActionError,
    AddedDocuments,
    ChunkingExperimentInfo,
    EmbeddingModel,
    EmbeddingsExperimentInfo,
    InvalidRequest,
    JobWatch,
    UnavailableError,
)

type Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler) -> httpx.Client:
    return httpx.Client(base_url="http://server", transport=httpx.MockTransport(handler))


class Seen:
    """Answers in order and records `METHOD path?query` and each body."""

    def __init__(self, *answers: httpx.Response) -> None:
        self.answers = iter(answers)
        self.requests: list[str] = []
        self.bodies: list[object] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        query = f"?{request.url.query.decode()}" if request.url.query else ""
        self.requests.append(f"{request.method} {request.url.path}{query}")
        self.bodies.append(json.loads(request.content) if request.content else None)
        return next(self.answers)


def test_data_selects_a_page_with_the_selection_and_the_experiment_to_leave_out() -> None:
    seen = Seen(httpx.Response(200, json={"total": 3, "sha256s": ["a", "b"], "pages": 2}))
    page = DataClient(_client(seen), "/data").select("parsed", {"sample": 3}, "c9", 1, 2)
    assert (page.total, page.sha256s, page.pages) == (3, ("a", "b"), 2)
    assert seen.requests == ["POST /data/documents/select"]
    assert seen.bodies == [
        {"universe": "parsed", "files": {"sample": 3}, "page": 1, "per_page": 2, "exclude_experiment": "c9"}
    ]


def test_a_selection_data_refuses_is_an_invalid_request() -> None:
    seen = Seen(httpx.Response(422, json={"detail": "month needs year"}))
    with pytest.raises(InvalidRequest, match="month needs year"):
        DataClient(_client(seen), "/data").select("parsed", {"all": True}, None, 1, 10)


def test_data_is_read_until_the_experiment_isnt_alive() -> None:
    seen = Seen(
        httpx.Response(404, json={"detail": "not yet"}),
        httpx.Response(200, json={"label": "EXPERIMENTO", "id": "c1", "properties": {"estado": "running"}}),
        httpx.Response(200, json={"id": "c1", "properties": {"estado": "partial", "error": None}}),
    )
    slept: list[float] = []
    state = DataClient(_client(seen), "/data", sleep=slept.append).wait_experiment("c1")
    assert (state.status, state.error, len(slept)) == ("partial", None, 2)
    assert seen.requests[0] == "GET /data/nodes/EXPERIMENTO/c1?omit=documentos&omit=resultados&omit=progreso"


def test_the_wait_stops_when_the_run_is_cancelled_or_too_long() -> None:
    watch = JobWatch()
    watch.cancel()
    with pytest.raises(ActionError, match="cancelled"):
        DataClient(_client(Seen()), "/data").wait_experiment("c1", watch)
    clock = iter([0.0, 10.0])
    running = httpx.Response(200, json={"properties": {"estado": "queued"}})
    client = DataClient(_client(Seen(running)), "/data", sleep=lambda _: None, clock=lambda: next(clock), timeout=5)
    with pytest.raises(UnavailableError, match="still running"):
        client.wait_experiment("c1")


def test_chunking_starts_an_experiment_without_waiting_for_it() -> None:
    seen = Seen(httpx.Response(409, json={"detail": "full"}), httpx.Response(202, json={"id": "c1"}))
    assert ChunkingClient(_client(seen), "/chunking", sleep=lambda _: None).start_experiment({"name": "x"}) == "c1"
    assert seen.requests == ["POST /chunking/experiments"] * 2


def test_chunking_says_an_experiments_status_and_parameters() -> None:
    view = {"id": "c1", "status": "finished", "chunking": {"chunker": "hybrid", "fit": []}}
    seen = Seen(httpx.Response(200, json=view), httpx.Response(404, json={"detail": "no"}))
    client = ChunkingClient(_client(seen), "/chunking")
    assert client.experiment_info("c1") == ChunkingExperimentInfo("c1", "finished", {"chunker": "hybrid", "fit": []})
    assert client.experiment_info("c2") is None


def test_chunking_adds_documents_and_resumes() -> None:
    seen = Seen(
        httpx.Response(202, json={"added": 2, "already": 1, "unparsed": 0, "total": 9}),
        httpx.Response(202, json={"id": "c1"}),
    )
    client = ChunkingClient(_client(seen), "/chunking")
    assert client.add_documents("c1", ["a", "b"]) == AddedDocuments(2, 1, 0, 9)
    client.resume_experiment("c1")
    assert seen.requests == ["POST /chunking/experiments/c1/documents", "POST /chunking/experiments/c1/resume"]
    assert seen.bodies[0] == {"sha256s": ["a", "b"], "simulate": False}


def test_chunking_gives_its_active_parameters() -> None:
    seen = Seen(httpx.Response(200, json={"chunking": {"tokenizer": "m", "max_tokens": 126}}))
    assert ChunkingClient(_client(seen), "/chunking").config() == {"tokenizer": "m", "max_tokens": 126}


def test_embeddings_reads_the_budgets_of_each_model() -> None:
    model = {"name": "e5", "default_tokens": 512, "max_tokens": 512, "passage_budget": 507}
    seen = Seen(httpx.Response(200, json=[model | {"default_passage_budget": None}]))
    assert EmbeddingsClient(_client(seen), "/embeddings").models() == [
        EmbeddingModel("e5", 512, 512, False, 507, None, None)
    ]


def test_embeddings_lists_the_experiments_of_a_chunking_experiment() -> None:
    seen = Seen(httpx.Response(200, json=[{"id": "e1", "model": "m", "status": "finished", "pending": ["a"]}]))
    found = EmbeddingsClient(_client(seen), "/embeddings").experiments_of("c1")
    assert found == [EmbeddingsExperimentInfo("e1", "m", "finished", 1)]
    assert seen.requests == ["GET /embeddings/experiments?chunking_experiment=c1"]


def test_resuming_an_embeddings_experiment_that_lacks_something_waits_its_turn() -> None:
    seen = Seen(
        httpx.Response(200, json={"id": "e1", "model": "m", "status": "finished", "pending": 2}),
        httpx.Response(409, json={"detail": "full"}),
        httpx.Response(202, json={"id": "e1"}),
        httpx.Response(200, json={"id": "e1", "status": "finished", "embedded": ["a"]}),
    )
    outcome = EmbeddingsClient(_client(seen), "/embeddings", sleep=lambda _: None).resume("e1")
    assert outcome.succeeded and outcome.sha256s == ("a",)
    assert seen.requests[1:3] == ["POST /embeddings/experiments/e1/resume"] * 2


def test_one_that_lacks_nothing_isnt_resumed() -> None:
    finished = httpx.Response(200, json={"id": "e1", "model": "m", "status": "finished", "pending": 0})
    seen = Seen(finished, finished)
    assert EmbeddingsClient(_client(seen), "/embeddings").resume("e1").succeeded
    assert all(r.startswith("GET") for r in seen.requests)


def test_without_pending_a_409_means_nothing_to_resume() -> None:
    seen = Seen(
        httpx.Response(200, json={"id": "e1", "config": {"model": "m"}, "status": "finished"}),
        httpx.Response(409, json={"detail": "nothing lacking"}),
        httpx.Response(200, json={"id": "e1", "status": "finished"}),
    )
    assert EmbeddingsClient(_client(seen), "/embeddings").resume("e1").succeeded


def test_an_official_run_with_another_model_says_it() -> None:
    seen = Seen(httpx.Response(202, json={"id": "r1"}), httpx.Response(200, json={"status": "finished"}))
    EmbeddingsClient(_client(seen), "/embeddings").embed_model(["a"], "bge")
    assert seen.bodies[0] == {"sha256s": ["a"], "model": "bge"}
