"""GraphExperimentStore over data's routes (FakeData behind an httpx.MockTransport): an experiment with an EXP_DOCUMENTO
per document (feature 055 part b), what depends on it, and deleting it."""

from collections.abc import Iterator

import httpx
import pytest
from fakes import FakeData

from chunking.adapters.data import GraphExperimentStore
from chunking.domain import ExperimentGraph, Parameters
from chunking.models import Chunk, ExperimentRequest, RequestedChunking

A, B = "a" * 64, "b" * 64
CHUNKS = [Chunk(0, "uno", "T\nuno", ["T"], [1], 3), Chunk(1, "dos", "U\ndos", ["U"], [2], 5)]


@pytest.fixture
def store(fake_data: FakeData) -> Iterator[GraphExperimentStore]:
    with httpx.Client(base_url="http://server", transport=httpx.MockTransport(fake_data.handle)) as client:
        yield GraphExperimentStore(client, "/data")


@pytest.fixture
def experiment(fake_data: FakeData, store: GraphExperimentStore) -> str:
    """e1 over A (chunked) and B (failed)."""
    for sha256 in (A, B):
        fake_data.nodes[("JSON", sha256)] = {"estado": "parseado"}
    request = ExperimentGraph.experiment("e1", _request(), 2, "2026")
    store.save(request)
    store.save(ExperimentGraph.document("e1", A, CHUNKS, None, 0.5))
    store.save(ExperimentGraph.document("e1", B, [], "bad", 0.1))
    return "e1"


def _request() -> ExperimentRequest:
    return ExperimentRequest("e1", "", Parameters.resolve(RequestedChunking(), "2"), [A, B])


def test_what_it_did_with_each_document_is_read_from_its_exp_documento(
    store: GraphExperimentStore, experiment: str
) -> None:
    uses = sorted(store.uses(experiment), key=lambda u: u.sha256)
    assert [(u.sha256, u.chunked, u.chunks, u.tokens) for u in uses] == [(A, True, 2, [3, 5]), (B, False, 0, [])]
    assert sorted(store.documents(experiment)) == [A, B]


def test_without_dependents_there_are_none(store: GraphExperimentStore, experiment: str) -> None:
    assert not store.dependents(experiment).any
    assert not store.dependents("nope").any  # no experiment: nothing depends on it


def test_embeddings_experiments_and_pipeline_iterations_are_its_dependents(
    fake_data: FakeData, store: GraphExperimentStore, experiment: str
) -> None:
    fake_data.nodes[("EXP_EMBEDDINGS", "emb1")] = {}
    fake_data.nodes[("PIPE_ITERACION", "it1")] = {}
    fake_data.link("EXP_USA", ("EXP_EMBEDDINGS", "emb1"), ("EXPERIMENTO", experiment))
    fake_data.link("PIPE_USA", ("PIPE_ITERACION", "it1"), ("EXPERIMENTO", experiment))
    found = store.dependents(experiment)
    assert (found.embeddings, found.pipeline) == (["emb1"], ["it1"])


def test_deleting_it_takes_its_documents_sections_chunks_and_vectors_and_never_the_json(
    fake_data: FakeData, store: GraphExperimentStore, experiment: str
) -> None:
    chunk = ("EXP_CHUNK", ExperimentGraph.chunk_id(experiment, A, 0))
    fake_data.nodes[("EXP_EMBED", "emb1:x")] = {}
    fake_data.link("EXP_TIENE_VECTOR", chunk, ("EXP_EMBED", "emb1:x"))
    assert store.delete(experiment)
    left = {label for label, _ in fake_data.nodes}
    assert left == {"JSON"}
    assert not store.delete(experiment)


def test_a_resumed_document_replaces_what_its_previous_try_left(
    fake_data: FakeData, store: GraphExperimentStore, experiment: str
) -> None:
    store.save(ExperimentGraph.document(experiment, A, CHUNKS[:1], None, 0.2))
    chunks = {id for label, id in fake_data.nodes if label == "EXP_CHUNK"}
    assert chunks == {ExperimentGraph.chunk_id(experiment, A, 0)}


def test_the_documents_of_an_experiment_come_from_the_ids_of_its_exp_documento(
    fake_data: FakeData, store: GraphExperimentStore, experiment: str
) -> None:
    for key in [k for k in fake_data.nodes if k[0] == "EXP_DOCUMENTO"]:
        fake_data.nodes[key] = {}  # nothing is read from the node itself (feature 059)
    assert sorted(store.documents(experiment)) == [A, B]


def test_every_parsed_document_is_listed_a_page_at_a_time(
    fake_data: FakeData, store: GraphExperimentStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("chunking.adapters.data.progress_client.GRAPH_PAGE_SIZE", 2)
    for sha256, state in ((A, "parseado"), (B, "parcial"), ("c" * 64, "parseado"), ("d" * 64, "error")):
        fake_data.nodes[("JSON", sha256)] = {"estado": state}
    assert store.parsed_documents() == [A, B, "c" * 64]  # in two pages; the one in error isn't parsed
    assert store.parsed_count() == 3
