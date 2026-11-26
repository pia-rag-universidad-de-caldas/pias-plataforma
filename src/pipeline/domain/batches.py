"""Freezing a batch: the ids a selection takes, page after page, so every iteration of a cycle works on the same."""

import hashlib
import random
from collections.abc import Callable

from pipeline.config import MAX_SELECT_PER_PAGE, SELECT_PER_PAGE
from pipeline.models import ActionError, Selection

# (page number, per_page) → (ids of that page, number of pages, marker that must not change between pages)
type PageFetch = Callable[[int, int], tuple[tuple[str, ...], int, str | None]]


def unique(ids: list[str]) -> list[str]:
    """Without repeats, in their first order."""
    return list(dict.fromkeys(ids))


def collect(selection: Selection, fetch: PageFetch) -> list[str]:
    """The ids of `selection.all` (every page) or of `selection.pages` (start..end, as far as there are pages).
    A marker that changes in the middle (ingesta reorganized) is an ActionError: the pages may have shifted."""
    per_page = selection.per_page or SELECT_PER_PAGE
    if per_page > MAX_SELECT_PER_PAGE:
        raise ActionError(f"per_page can't be more than {MAX_SELECT_PER_PAGE}")
    page = selection.pages.start if selection.pages else 1
    last = selection.pages.end if selection.pages else None
    ids: list[str] = []
    marker: str | None = None
    first = True
    while last is None or page <= last:
        found, pages, current = fetch(page, per_page)
        if first:
            marker, first = current, False
        elif current != marker:
            raise ActionError("ingesta was reorganized during the selection (`reorganizado` changed): repeat it")
        ids += found
        if page >= pages:
            break
        page += 1
    return unique(ids)


def sampled(ids: list[str], size: int, seed: int | None) -> list[str]:
    """`size` of `ids` at random (all of them if there are fewer), in the order by sha256. With `seed` the same ids
    always give the same sample: ordered by the hash of seed + sha256 (as data samples, feature 062)."""
    ordered = sorted(set(ids))
    if size >= len(ordered):
        return ordered
    if seed is None:
        chosen = random.sample(ordered, size)
    else:
        chosen = sorted(ordered, key=lambda s: hashlib.sha256(f"{seed}{s}".encode()).hexdigest())[:size]
    return sorted(chosen)
