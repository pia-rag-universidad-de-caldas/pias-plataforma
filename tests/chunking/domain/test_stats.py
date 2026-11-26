"""token_stats (feature 043): the token sizes of an experiment's chunks."""

from chunking.domain import token_stats
from chunking.models import TokenStats


def test_token_stats_of_nothing_is_none() -> None:
    assert token_stats([]) is None


def test_token_stats_gives_min_mean_p90_and_max() -> None:
    assert token_stats(list(range(1, 11))) == TokenStats(1, 5.5, 9, 10)
