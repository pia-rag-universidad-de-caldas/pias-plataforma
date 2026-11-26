"""The token limit: asked or the model's default, never past what the model admits."""

import pytest

from embeddings.config import DEFAULT_MODEL, MODELS
from embeddings.domain import PassageBudgets, passage_budgets, token_limit
from embeddings.domain.events import HEADING_TOKENS
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


def test_the_passage_budgets_take_out_the_special_tokens_and_the_prefix() -> None:
    """Feature 062: e5's `passage: ` (say 3 tokens), its 512 positions also its default."""
    budgets = passage_budgets(MODELS["intfloat/multilingual-e5-base"], 3)
    assert budgets == PassageBudgets(507, 507, 512 - HEADING_TOKENS - 5)


def test_the_official_budget_keeps_the_default_when_the_course_still_fits() -> None:
    assert passage_budgets(MODELS[DEFAULT_MODEL], 0) == PassageBudgets(510, 126, 126)


def test_without_counting_the_prefix_there_are_no_budgets() -> None:
    assert passage_budgets(MODELS[DEFAULT_MODEL], None) == PassageBudgets(None, None, None)
