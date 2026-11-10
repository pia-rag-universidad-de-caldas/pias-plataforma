"""The token limit: asked or the model's default, never past what the model admits."""

import pytest

from embeddings.config import DEFAULT_MODEL, MODELS
from embeddings.domain import token_limit
from embeddings.models import InvalidLimit


def test_without_asking_it_is_the_model_default() -> None:
    assert token_limit(DEFAULT_MODEL, None) == MODELS[DEFAULT_MODEL].default_tokens


def test_a_limit_in_range_is_kept() -> None:
    assert token_limit(DEFAULT_MODEL, 256) == 256


@pytest.mark.parametrize("asked", [0, MODELS[DEFAULT_MODEL].max_tokens + 1])
def test_a_limit_out_of_range_is_refused(asked: int) -> None:
    with pytest.raises(InvalidLimit):
        token_limit(DEFAULT_MODEL, asked)


def test_a_model_that_is_not_served_is_refused() -> None:
    with pytest.raises(InvalidLimit, match="isn't served"):
        token_limit("someone/else", None)
