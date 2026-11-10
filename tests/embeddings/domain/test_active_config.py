"""The active configuration: the stored one while it works, otherwise the default."""

from fakes import FakeVectorSink

from embeddings.config import DEFAULT_MODEL, MODELS
from embeddings.domain import resolve
from embeddings.models import ConfigOrigin, EmbeddingConfig


def test_without_a_stored_one_it_is_the_default_model_with_its_default_limit() -> None:
    assert resolve(FakeVectorSink()) == EmbeddingConfig(DEFAULT_MODEL, MODELS[DEFAULT_MODEL].default_tokens)


def test_a_stored_one_that_works_is_used() -> None:
    store = FakeVectorSink()
    store.stored = EmbeddingConfig(DEFAULT_MODEL, 256, ConfigOrigin.MANUAL)
    assert resolve(store).max_tokens == 256


def test_a_stored_one_with_a_model_no_longer_served_gives_the_default() -> None:
    store = FakeVectorSink()
    store.stored = EmbeddingConfig("gone/model", 128, ConfigOrigin.MANUAL)
    assert resolve(store).model == DEFAULT_MODEL
