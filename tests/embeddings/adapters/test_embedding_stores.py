"""The ports over data (httpx.MockTransport over FakeData): the chunks in order, the vectors with merge, the errors."""

import httpx
import pytest
from fakes import FakeData, FakeEmbedder, chunked_document

from embeddings.adapters import HttpSession
from embeddings.config import DEFAULT_MODEL
from embeddings.domain import ExperimentRunner, Runner, fingerprint_key, vector_property
from embeddings.models import (
    DocumentError,
    EmbeddingConfig,
    ExperimentRequest,
    GraphBatch,
    GraphLabel,
    GraphNode,
    NodeKey,
    RunRequest,
    UpstreamDown,
    VectorIndexSpec,
)


def session(data: FakeData) -> HttpSession:
    return HttpSession("http://server", transport=httpx.MockTransport(data.handle))


def test_the_chunks_of_a_document_come_in_section_and_index_order(fake_data: FakeData) -> None:
    ids = chunked_document(fake_data, "a", [["uno", "dos"], ["tres"]])
    with session(fake_data) as s:
        found = s.source.chunks("a")
    assert [c.id for c in found] == ids
    assert found[0].text == "t0\nuno"  # texto_contextualizado: with its headings


def test_a_document_says_whether_it_is_chunked(fake_data: FakeData) -> None:
    chunked_document(fake_data, "a", [["uno"]], state="error")
    with session(fake_data) as s:
        document = s.source.document("a")
        assert document is not None and not document.chunked
        assert s.source.document("b") is None


def test_the_chunks_of_an_experiment_by_document(fake_data: FakeData) -> None:
    chunked_document(fake_data, "a", [["uno"], ["dos"]], experiment="c1")
    chunked_document(fake_data, "b", [["tres"]], experiment="c1")
    with session(fake_data) as s:
        found = s.source.experiment_chunks("c1")
        assert s.source.experiment_status("c1") == "finished" and s.source.experiment_status("x") is None
    assert {sha256: [c.text for c in chunks] for sha256, chunks in found.items()} == {
        "a": ["t0\nuno", "t1\ndos"],
        "b": ["t0\ntres"],
    }


def test_data_down_is_upstream_down_and_a_refusal_a_document_error(fake_data: FakeData) -> None:
    batch = GraphBatch([GraphNode(NodeKey(GraphLabel.FRAGMENTOS, "x"), {"embedding": [1.0]})])
    with session(fake_data) as s:
        fake_data.refuse = {"x"}
        with pytest.raises(DocumentError):
            s.vectors.save(batch)
        fake_data.down = True
        with pytest.raises(UpstreamDown):
            s.source.chunks("a")


def test_an_index_with_another_definition_stops_the_run(fake_data: FakeData) -> None:
    fake_data.indexes["vec_x"] = {"name": "vec_x", "label": "EXP_EMBED", "property": "embedding_x_3", "dimensions": 3}
    with session(fake_data) as s, pytest.raises(UpstreamDown, match="409"):
        s.vectors.ensure_index(VectorIndexSpec("vec_x", "FRAGMENTOS", "embedding_x_384", 384))


def test_the_documents_of_each_fingerprint_are_counted_without_their_parse(fake_data: FakeData) -> None:
    key = fingerprint_key(DEFAULT_MODEL)
    fake_data.nodes[("JSON", "a")] = {key: "sha256:a", "documento": "big"}
    fake_data.nodes[("JSON", "b")] = {"documento": "big"}
    with session(fake_data) as s:
        assert s.source.fingerprint_counts() == {key: 1}
        assert s.source.with_fingerprint(key) == ["a"]


def test_dropping_an_index_that_does_not_exist_is_false(fake_data: FakeData) -> None:
    with session(fake_data) as s:
        assert not s.vectors.drop_index("vec_x", True)
    assert fake_data.dropped == [("vec_x", True)]


@pytest.mark.integration
def test_scenario_a_run_over_data_keeps_the_text_and_deletes_nothing(fake_data: FakeData) -> None:
    ids = chunked_document(fake_data, "a", [["uno", "dos"]])
    config = EmbeddingConfig(DEFAULT_MODEL, 128)
    with session(fake_data) as s:
        progress = Runner.run(s.source, s.vectors, FakeEmbedder(), config, RunRequest(["a"]))
        again = Runner.run(s.source, s.vectors, FakeEmbedder(), config, RunRequest(["a"]))
    assert (progress.embedded, again.unchanged) == (1, 1)
    chunk = fake_data.nodes[("FRAGMENTOS", ids[0])]
    assert chunk["texto"] == "uno" and chunk[vector_property(DEFAULT_MODEL)] == [2.0, 1.0]  # t0 + uno: 2 words
    assert fake_data.nodes[("JSON", "a")]["documento"] == "big"  # the parse stays
    assert all("replace_from" not in batch or batch["replace_from"] is None for batch in fake_data.batches)


@pytest.mark.integration
def test_scenario_two_experiments_keep_a_vector_each_and_deleting_one_leaves_the_other(
    fake_data: FakeData,
) -> None:
    official = chunked_document(fake_data, "a", [["uno"]])
    chunked_document(fake_data, "a", [["uno"]], experiment="c1")
    property = vector_property(DEFAULT_MODEL)
    with session(fake_data) as s:
        for id in ("e1", "e2"):
            fake_data.nodes[("EXP_EMBEDDINGS", id)] = {"estado": "running"}  # its record: the route saves it first
            config = ExperimentRunner.config(ExperimentRequest("c1", DEFAULT_MODEL), id)
            ExperimentRunner.run(s.source, s.vectors, FakeEmbedder(), config, "c1")
        assert property not in fake_data.nodes[("FRAGMENTOS", official[0])]
        assert fingerprint_key(DEFAULT_MODEL) not in fake_data.nodes[("JSON", "a")]
        assert fake_data.nodes[("EXP_EMBED", "e1:c1:a:0")][property] == [2.0, 1.0]
        assert ("EXP_TIENE_VECTOR", "EXP_CHUNK", "c1:a:0", "EXP_EMBED", "e2:c1:a:0") in fake_data.links
        s.vectors.save(ExperimentRunner.cleared("e1"))
    assert ("EXP_EMBED", "e1:c1:a:0") not in fake_data.nodes and ("EXP_EMBED", "e2:c1:a:0") in fake_data.nodes
    assert "embedding" not in fake_data.nodes[("EXP_CHUNK", "c1:a:0")]  # the chunk itself never holds a vector
