"""A document's fingerprint changes with what its vectors depend on: the chunks, the model and the version."""

import pytest

import embeddings.domain.fingerprint as module
from embeddings.domain import document_fingerprint
from embeddings.models import EmbeddableChunk

CHUNKS = [EmbeddableChunk("a:0", "uno"), EmbeddableChunk("a:1", "dos")]


def test_the_text_changes_it() -> None:
    other = [CHUNKS[0], EmbeddableChunk("a:1", "tres")]
    assert document_fingerprint("m", CHUNKS) != document_fingerprint("m", other)


def test_the_model_changes_it() -> None:
    assert document_fingerprint("m", CHUNKS) != document_fingerprint("n", CHUNKS)


def test_the_version_changes_it(monkeypatch: pytest.MonkeyPatch) -> None:
    before = document_fingerprint("m", CHUNKS)
    monkeypatch.setattr(module, "MODEL_VERSION", 99)
    assert document_fingerprint("m", CHUNKS) != before
