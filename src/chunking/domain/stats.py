"""The token sizes of an experiment's chunks (feature 043)."""

import math

from chunking.models import TokenStats


def token_stats(values: list[int]) -> TokenStats | None:
    if not values:
        return None
    ordered = sorted(values)
    p90 = ordered[max(0, math.ceil(0.9 * len(ordered)) - 1)]
    return TokenStats(ordered[0], round(sum(ordered) / len(ordered), 1), p90, ordered[-1])
