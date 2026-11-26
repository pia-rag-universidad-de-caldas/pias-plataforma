"""ExperimentRunner (laboratory): the chunks of a chunking experiment, never the official ones."""

import pytest
from fakes import FakeChunkSource, FakeEmbedder, FakeVectorSink

from embeddings.config import DEFAULT_MODEL
from embeddings.domain import ExperimentRunner, UnfinishedExperiment, UnknownExperiment
from embeddings.models import (
    ConfigOrigin,
    EmbeddableChunk,
    ExperimentRequest,
    GraphBatch,
    GraphLabel,
    InvalidLimit,
    NodeKey,
    RunProgress,
)

REQUEST = ExperimentRequest("c1", DEFAULT_MODEL, 6)


def source_with(chunks: dict[str, list[EmbeddableChunk]], status: str = "finished") -> FakeChunkSource:
    source = FakeChunkSource()
    source.experiments["c1"] = status
    source.experiment_of["c1"] = chunks
    return source


def test_it_embeds_the_experiment_chunks_in_embeds_of_its_own() -> None:
    source = source_with({"a": [EmbeddableChunk("c1:a:0", "uno")], "b": [EmbeddableChunk("c1:b:0", "dos tres")]})
    sink = FakeVectorSink()
    config = ExperimentRunner.config(REQUEST, "e1")
    progress = ExperimentRunner.run(source, sink, FakeEmbedder(), config, "c1")
    assert (progress.embedded, progress.chunks) == (2, 2)
    nodes = [n for batch in sink.batches for n in batch.nodes]
    assert {n.key.label for n in nodes} == {GraphLabel.EXP_EMBED}  # never the official JSON nor FRAGMENTOS
    assert sorted(n.key.id for n in nodes) == ["e1:c1:a:0", "e1:c1:b:0"]
    assert [i.label for i in sink.indexes] == ["EXP_EMBED"]


def test_a_resume_embeds_only_the_documents_it_is_given_over_the_progress_it_had() -> None:
    """Feature 062."""
    source = source_with({"a": [EmbeddableChunk("c1:a:0", "uno")], "b": [EmbeddableChunk("c1:b:0", "dos")]})
    sink = FakeVectorSink()
    config = ExperimentRunner.config(REQUEST, "e1")
    start = RunProgress(total=2, embedded=1, chunks=1)
    progress = ExperimentRunner.run(source, sink, FakeEmbedder(), config, "c1", documents=["b"], start=start)
    assert (progress.total, progress.embedded, progress.chunks) == (2, 2, 2)
    assert [n.key.id for batch in sink.batches for n in batch.nodes] == ["e1:c1:b:0"]


@pytest.mark.parametrize(
    ("missing", "only", "pending"), [(["b"], (), ["b"]), (None, (), ["a", "b"]), (["a", "b"], ("b", "z"), ["b"])]
)
def test_what_a_resume_takes(missing: list[str] | None, only: tuple[str, ...], pending: list[str]) -> None:
    """What data says the experiment lacks (all of its chunking experiment if data doesn't know it), or only those."""
    source = source_with({"a": [], "b": []})
    if missing is not None:
        source.missing_of["e1"] = missing
    assert ExperimentRunner.pending(source, "e1", "c1", only) == pending


def test_its_configuration_is_checked_before_anything_runs() -> None:
    with pytest.raises(InvalidLimit):
        ExperimentRunner.config(ExperimentRequest("c1", DEFAULT_MODEL, 100_000), "e1")
    assert ExperimentRunner.config(REQUEST, "e1").origin is ConfigOrigin.EXPERIMENT


def test_a_chunking_experiment_that_does_not_exist_is_unknown() -> None:
    with pytest.raises(UnknownExperiment):
        ExperimentRunner.check(FakeChunkSource(), "c1")


@pytest.mark.parametrize("status", ["queued", "running", "failed", "interrupted"])
def test_a_chunking_experiment_that_did_not_end_well_is_refused(status: str) -> None:
    with pytest.raises(UnfinishedExperiment):
        ExperimentRunner.check(source_with({}, status=status), "c1")


def test_a_partial_chunking_experiment_can_be_embedded() -> None:
    ExperimentRunner.check(source_with({}, status="partial"), "c1")  # what it chunked (feature 059)


def test_it_reads_the_chunks_of_one_document_at_a_time() -> None:
    source = source_with({"b": [EmbeddableChunk("c1:b:0", "dos")], "a": [EmbeddableChunk("c1:a:0", "uno")]})
    reads: list[tuple[str, int]] = []

    class Watched(FakeVectorSink):
        def save(self, batch: GraphBatch) -> None:
            reads.append((source.experiment_reads[-1], len(source.experiment_reads)))
            super().save(batch)

    ExperimentRunner.run(source, Watched(), FakeEmbedder(), ExperimentRunner.config(REQUEST, "e1"), "c1")
    assert reads == [("a", 1), ("b", 2)]  # each document is saved before the next one is read


def test_a_document_without_chunks_is_skipped() -> None:
    source = source_with({"a": [EmbeddableChunk("c1:a:0", "uno")], "b": []})
    progress = ExperimentRunner.run(
        source, FakeVectorSink(), FakeEmbedder(), ExperimentRunner.config(REQUEST, "e1"), "c1"
    )
    assert (progress.total, progress.embedded, progress.skipped, progress.done) == (2, 1, 1, 2)


def test_two_experiments_over_the_same_chunks_keep_a_vector_each_even_with_the_same_model() -> None:
    source = source_with({"a": [EmbeddableChunk("c1:a:0", "uno")]})
    sink = FakeVectorSink()
    for id in ("e1", "e2"):
        ExperimentRunner.run(source, sink, FakeEmbedder(), ExperimentRunner.config(REQUEST, id), "c1")
    ids = [n.key.id for batch in sink.batches for n in batch.nodes]
    assert ids == ["e1:c1:a:0", "e2:c1:a:0"]
    assert ExperimentRunner.cleared("e1").replace_from == NodeKey(GraphLabel.EXP_EMBEDDINGS, "e1")  # not e2's


def test_a_long_chunk_fails_only_its_document() -> None:
    long = [EmbeddableChunk("c1:a:0", "uno dos tres cuatro cinco")]
    source = source_with({"a": long, "b": [EmbeddableChunk("c1:b:0", "dos")]})
    progress = ExperimentRunner.run(
        source, FakeVectorSink(), FakeEmbedder(), ExperimentRunner.config(REQUEST, "e1"), "c1"
    )
    assert (progress.errors, progress.embedded) == (1, 1)


def test_deleting_removes_only_the_vectors_it_generated() -> None:
    batch = ExperimentRunner.cleared("e1")
    assert (batch.nodes, batch.replace_from) == ([], NodeKey(GraphLabel.EXP_EMBEDDINGS, "e1"))


def test_apply_copies_model_and_limit_to_the_active_configuration() -> None:
    store = FakeVectorSink()
    applied = ExperimentRunner.apply(store, ExperimentRunner.config(REQUEST, "e1"))
    assert store.stored == applied
    assert (applied.model, applied.max_tokens, applied.experiment) == (DEFAULT_MODEL, 6, "e1")
