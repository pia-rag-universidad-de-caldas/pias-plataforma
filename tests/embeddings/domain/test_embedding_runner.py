"""Runner (production): what changed is embedded, a bad document fails alone, the machine stops it, nothing is cut."""

import pytest
from fakes import FakeChunkSource, FakeEmbedder, FakeVectorSink

from embeddings.config import DEFAULT_MODEL
from embeddings.domain import RunEvents, Runner, document_fingerprint, fingerprint_key, limit_key, vector_property
from embeddings.models import (
    DocumentFailure,
    EmbeddingConfig,
    GraphLabel,
    NodeWrite,
    RunProgress,
    RunRequest,
    UpstreamDown,
)

CONFIG = EmbeddingConfig(DEFAULT_MODEL, 6)  # up to 4 words (+2 special tokens)
KEY = fingerprint_key(DEFAULT_MODEL)
OTHER = "intfloat/multilingual-e5-base"  # a model with prefixes (feature 055)


def run(
    source: FakeChunkSource, sink: FakeVectorSink, request: RunRequest, embedder: FakeEmbedder | None = None
) -> tuple[RunProgress, list[DocumentFailure], list[str]]:
    failures: list[DocumentFailure] = []
    embedded: list[str] = []
    events = RunEvents(failure=failures.append, embedded=embedded.append)
    progress = Runner.run(source, sink, embedder or FakeEmbedder(), CONFIG, request, events)
    return progress, failures, embedded


def test_a_chunked_document_gets_its_vectors_and_its_fingerprint() -> None:
    source, sink = FakeChunkSource(), FakeVectorSink()
    source.add("a", ["uno dos", "tres"])
    progress, _, embedded = run(source, sink, RunRequest(["a"]))
    assert (progress.embedded, progress.chunks, embedded) == (1, 2, ["a"])
    [batch] = sink.batches
    assert all(node.mode is NodeWrite.MERGE for node in batch.nodes)  # the text stays
    property = vector_property(DEFAULT_MODEL)
    vectors = {n.key.id: n.properties[property] for n in batch.nodes if n.key.label is GraphLabel.FRAGMENTOS}
    assert vectors == {"a:0": [2.0, 1.0], "a:1": [1.0, 1.0]}
    document = next(n.properties for n in batch.nodes if n.key.label is GraphLabel.JSON)
    assert document[fingerprint_key(DEFAULT_MODEL)] == document_fingerprint(DEFAULT_MODEL, source.chunks("a"))
    assert document[limit_key(DEFAULT_MODEL)] == 6  # the limit the run used


def test_the_index_of_the_model_is_asked_for_before_any_vector() -> None:
    sink = FakeVectorSink()
    run(FakeChunkSource(), sink, RunRequest(["a"]))
    assert [i.label for i in sink.indexes] == ["FRAGMENTOS"]


def test_what_did_not_change_is_not_embedded_again_but_has_vectors() -> None:
    source, sink = FakeChunkSource(), FakeVectorSink()
    source.add("a", ["uno"])
    source.add("a", ["uno"], fingerprints={KEY: document_fingerprint(DEFAULT_MODEL, source.chunks("a"))})
    progress, _, embedded = run(source, sink, RunRequest(["a"]))
    assert (progress.unchanged, progress.embedded, sink.batches, embedded) == (1, 0, [], ["a"])


def test_force_embeds_again_what_did_not_change() -> None:
    source, sink = FakeChunkSource(), FakeVectorSink()
    source.add("a", ["uno"])
    source.add("a", ["uno"], fingerprints={KEY: document_fingerprint(DEFAULT_MODEL, source.chunks("a"))})
    progress, _, _ = run(source, sink, RunRequest(["a"], force=True))
    assert progress.embedded == 1 and len(sink.batches) == 1


def test_a_document_not_chunked_waits() -> None:
    source, sink = FakeChunkSource(), FakeVectorSink()
    source.add("a", ["uno"], chunked=False)
    progress, failures, _ = run(source, sink, RunRequest(["a"]))
    assert (progress.skipped, failures, sink.batches) == (1, [], [])


def test_a_sha256_without_json_is_missing() -> None:
    progress, failures, _ = run(FakeChunkSource(), FakeVectorSink(), RunRequest(["a"]))
    assert progress.missing == 1 and [f.sha256 for f in failures] == ["a"]


def test_a_chunk_over_the_limit_fails_its_document_without_writing_and_the_others_go_on() -> None:
    source, sink = FakeChunkSource(), FakeVectorSink()
    source.add("a", ["uno dos tres cuatro cinco"])  # 5 words + 2 > 6
    source.add("b", ["uno"])
    embedder = FakeEmbedder()
    progress, failures, embedded = run(source, sink, RunRequest(["a", "b"]), embedder)
    assert (progress.errors, progress.embedded, embedded) == (1, 1, ["b"])
    assert "over 6 tokens" in failures[0].error
    assert [texts for _, texts, _ in embedder.calls] == [["uno"]]  # never cut: a's never reached the model


def test_data_refusing_a_document_fails_only_that_one() -> None:
    source, sink = FakeChunkSource(), FakeVectorSink()
    source.add("a", ["uno"])
    source.add("b", ["dos"])
    sink.refuse = {"a"}
    progress, failures, embedded = run(source, sink, RunRequest(["a", "b"]))
    assert (progress.errors, embedded, failures[0].sha256) == (1, ["b"], "a")


def test_the_machine_down_stops_the_run_and_marks_no_document() -> None:
    source, sink, embedder = FakeChunkSource(), FakeVectorSink(), FakeEmbedder()
    source.add("a", ["uno"])
    embedder.down = True
    failures: list[DocumentFailure] = []
    with pytest.raises(UpstreamDown):
        Runner.run(source, sink, embedder, CONFIG, RunRequest(["a"]), RunEvents(failure=failures.append))
    assert (failures, sink.batches) == ([], [])


def test_simulate_checks_the_lengths_but_writes_nothing() -> None:
    source, sink, embedder = FakeChunkSource(), FakeVectorSink(), FakeEmbedder()
    source.add("a", ["uno"])
    source.add("b", ["uno dos tres cuatro cinco"])
    progress, _, _ = run(source, sink, RunRequest(["a", "b"], simulate=True), embedder)
    assert (progress.embedded, progress.errors) == (1, 1)
    assert (sink.batches, sink.indexes, embedder.calls) == ([], [], [])


def test_a_repeated_sha256_goes_once() -> None:
    source, sink = FakeChunkSource(), FakeVectorSink()
    source.add("a", ["uno"])
    progress, _, _ = run(source, sink, RunRequest(["a", "a"]))
    assert (progress.total, progress.embedded, len(sink.batches)) == (1, 1, 1)


def test_another_model_has_its_own_fingerprint_so_it_embeds_next_to_the_active_one() -> None:
    """Feature 055: the active model's fingerprint doesn't make another model's run unchanged."""
    source, sink = FakeChunkSource(), FakeVectorSink()
    source.add("a", ["uno"])
    source.add("a", ["uno"], fingerprints={KEY: document_fingerprint(DEFAULT_MODEL, source.chunks("a"))})
    progress = Runner.run(source, sink, FakeEmbedder(), EmbeddingConfig(OTHER, 512), RunRequest(["a"]))
    assert progress.embedded == 1
    [batch] = sink.batches
    fragment = next(n for n in batch.nodes if n.key.label is GraphLabel.FRAGMENTOS)
    assert list(fragment.properties) == [vector_property(OTHER)]  # the active model's vectors aren't touched
    assert [i.property for i in sink.indexes] == [vector_property(OTHER)]


def test_a_model_with_a_passage_prefix_reads_it_and_counts_it() -> None:
    source, sink, embedder = FakeChunkSource(), FakeVectorSink(), FakeEmbedder()
    source.add("a", ["uno dos tres"])  # 3 words + "passage:" + 2 special = 6
    Runner.run(source, sink, embedder, EmbeddingConfig(OTHER, 6), RunRequest(["a"]))
    assert [texts for _, texts, _ in embedder.calls] == [["passage: uno dos tres"]]
    source.add("b", ["uno dos tres cuatro"])  # with the prefix, 7 > 6
    progress = Runner.run(source, sink, embedder, EmbeddingConfig(OTHER, 6), RunRequest(["b"]))
    assert progress.errors == 1
