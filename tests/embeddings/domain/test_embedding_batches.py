"""The batches of vectors: always merge; the model in the property's name; an experiment never carries the official
JSON, and only deleting one has a replace_from (feature 055)."""

from embeddings.config import DEFAULT_MODEL
from embeddings.domain import (
    cleared_batch,
    document_batch,
    experiment_batch,
    fingerprint_key,
    limit_key,
    unfingerprinted_batch,
    vector_property,
)
from embeddings.models import EmbeddableChunk, EmbeddingConfig, GraphLabel, GraphRelation, NodeKey, NodeWrite

CHUNKS = [EmbeddableChunk("a:0", "uno")]
CONFIG = EmbeddingConfig(DEFAULT_MODEL, 128, experiment="e1")


def test_a_document_batch_merges_its_chunks_and_its_json() -> None:
    batch = document_batch("a", CHUNKS, [[1.0]], CONFIG, "sha256:x")
    assert [(n.key.label, n.mode) for n in batch.nodes] == [
        (GraphLabel.FRAGMENTOS, NodeWrite.MERGE),
        (GraphLabel.JSON, NodeWrite.MERGE),
    ]
    assert batch.replace_from is None  # saving vectors deletes nothing


def test_a_document_batch_writes_the_model_property_and_fingerprint() -> None:
    fragment, document = document_batch("a", CHUNKS, [[1.0]], CONFIG, "sha256:x").nodes
    assert dict(fragment.properties) == {vector_property(DEFAULT_MODEL): [1.0]}
    assert (document.properties[fingerprint_key(DEFAULT_MODEL)], document.properties[limit_key(DEFAULT_MODEL)]) == (
        "sha256:x",
        128,
    )


def test_an_experiment_batch_has_one_embed_per_chunk_linked_to_both() -> None:
    batch = experiment_batch(CHUNKS, [[1.0]], CONFIG)
    assert [n.key for n in batch.nodes] == [NodeKey(GraphLabel.EXP_EMBED, "e1:a:0")]
    assert {(link.type, link.source.label) for link in batch.links} == {
        (GraphRelation.EXP_TIENE_VECTOR, GraphLabel.EXP_CHUNK),
        (GraphRelation.EXP_GENERA_VECTOR, GraphLabel.EXP_EMBEDDINGS),
    }


def test_deleting_an_experiment_replaces_from_its_record() -> None:
    assert cleared_batch("e1").replace_from == NodeKey(GraphLabel.EXP_EMBEDDINGS, "e1")


def test_dropping_a_model_nulls_its_fingerprint() -> None:
    [node] = unfingerprinted_batch(["a"], DEFAULT_MODEL).nodes
    assert dict(node.properties) == {fingerprint_key(DEFAULT_MODEL): None, limit_key(DEFAULT_MODEL): None}
