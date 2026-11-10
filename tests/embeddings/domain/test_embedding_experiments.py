"""ExperimentRunner (laboratory): the chunks of a chunking experiment, never the official ones."""

import pytest
from fakes import FakeChunkSource, FakeEmbedder, FakeVectorSink

from embeddings.config import DEFAULT_MODEL
from embeddings.domain import ExperimentRunner, UnfinishedExperiment, UnknownExperiment
from embeddings.models import ConfigOrigin, EmbeddableChunk, ExperimentRequest, GraphLabel, InvalidLimit, NodeKey

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


def test_its_configuration_is_checked_before_anything_runs() -> None:
    with pytest.raises(InvalidLimit):
        ExperimentRunner.config(ExperimentRequest("c1", DEFAULT_MODEL, 100_000), "e1")
    assert ExperimentRunner.config(REQUEST, "e1").origin is ConfigOrigin.EXPERIMENT


def test_a_chunking_experiment_that_does_not_exist_is_unknown() -> None:
    with pytest.raises(UnknownExperiment):
        ExperimentRunner.check(FakeChunkSource(), "c1")


def test_a_chunking_experiment_that_did_not_finish_is_refused() -> None:
    with pytest.raises(UnfinishedExperiment):
        ExperimentRunner.check(source_with({}, status="running"), "c1")


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
