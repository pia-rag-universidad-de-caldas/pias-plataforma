"""The only page loop of the HTTP clients (feature 026)."""

from collections.abc import Callable, Iterator, Mapping

from .base_client import Json


def paginate(
    fetch: Callable[[int], Json],
    pages_key: str,
    error: type[Exception],
    first: int = 1,
    last: int | None = None,
) -> Iterator[Mapping[str, Json]]:
    """Page after page of `fetch(page)`, from `first` to `last` (or to the end), each asked only when the previous one
    was consumed. The number of pages is `pages_key` of the first answer; an answer that isn't an object, or a first
    one without it, raises `error`. Page 1 is always yielded (even with no pages); a later `first` beyond the last
    page yields nothing."""
    page, pages = first, first
    while page <= pages and (last is None or page <= last):
        body = fetch(page)
        if not isinstance(body, Mapping):
            raise error(f"page {page} isn't an object: {body!r}")
        if page == first:
            try:
                pages = int(body[pages_key])
            except (KeyError, TypeError, ValueError) as e:
                raise error(f"the first page has no number of pages ({pages_key!r}): {e}") from e
            if page > max(pages, 1):
                return
        yield body
        page += 1
