"""Parameters.resolve (feature 025): the defaults and limits of each strategy; a value a strategy doesn't use is an
error."""

import pytest

from chunking.domain import InvalidParameters, Parameters
from chunking.models import (
    ChunkingStrategy,
    RequestedStrategy,
)


def test_parameters_take_defaults_and_only_what_the_strategy_uses() -> None:
    hybrid = Parameters.resolve(RequestedStrategy())
    assert hybrid.strategy is ChunkingStrategy.HYBRID and hybrid.max_tokens == 512 and hybrid.overlap_tokens is None
    element = Parameters.resolve(RequestedStrategy(strategy=ChunkingStrategy.ELEMENT))
    assert element.max_tokens is None and element.merge_peers is None
    fixed = Parameters.resolve(RequestedStrategy(strategy=ChunkingStrategy.FIXED, max_tokens=100, overlap_tokens=20))
    assert (fixed.max_tokens, fixed.overlap_tokens) == (100, 20)


@pytest.mark.parametrize(
    ("asked", "message"),
    [
        (RequestedStrategy(strategy=ChunkingStrategy.ELEMENT, max_tokens=100), "doesn't use max_tokens"),
        (RequestedStrategy(overlap_tokens=10), "doesn't use overlap_tokens"),
        (RequestedStrategy(tokenizer="gpt2"), "isn't allowed"),
        (RequestedStrategy(max_tokens=8), "max_tokens must be between"),
        (
            RequestedStrategy(strategy=ChunkingStrategy.FIXED, max_tokens=100, overlap_tokens=100),
            "less than max_tokens",
        ),
        (RequestedStrategy(strategy=ChunkingStrategy.SEMANTIC, embedding_model="x"), "isn't allowed"),
        (RequestedStrategy(strategy=ChunkingStrategy.SEMANTIC, similarity_threshold=1.5), "between 0 and 1"),
    ],
)
def test_parameters_never_ignore_a_wrong_value(asked: RequestedStrategy, message: str) -> None:
    with pytest.raises(InvalidParameters, match=message):
        Parameters.resolve(asked)
