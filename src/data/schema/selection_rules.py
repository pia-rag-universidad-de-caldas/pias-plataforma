"""The rules of a selection of documents (feature 062: POST /documents/select), without the API: which fields go
together. Exactly one mode (`all`, `sha256s`, `pages` or `sample`); `per_page` only with `pages`, which needs it;
`seed` only with `sample`; the filters (over the document's RAW) only with `all`, `pages` or `sample`; `month` only
with `year` and `week` only with `month`. There is no filter by PIAA code: a code is a single document (its versions),
not a group to choose from."""

from dataclasses import dataclass

MODES = ("all", "sha256s", "pages", "sample")


@dataclass(frozen=True)
class Selection:
    """What a selection asks for, already read: `pages` is (from, to), both included, from 1."""

    all: bool = False
    sha256s: tuple[str, ...] = ()
    pages: tuple[int, int] | None = None
    per_page: int | None = None
    sample: int | None = None
    seed: int | None = None
    types: tuple[str, ...] = ()
    year: int | None = None
    month: int | None = None  # 1-12: the leading number of the RAW's `mes` (11_Noviembre)
    week: str | None = None  # the RAW's `semana`, as stored (Semana_02)

    @property
    def filtered(self) -> bool:
        return bool(self.types) or any(v is not None for v in (self.year, self.month, self.week))

    @property
    def modes(self) -> list[str]:
        given = [self.all, bool(self.sha256s), self.pages is not None, self.sample is not None]
        return [mode for mode, on in zip(MODES, given, strict=True) if on]


def selection_problem(selection: Selection) -> str | None:
    """The first rule the selection breaks, in words; None if it follows them all."""
    modes = selection.modes
    if len(modes) != 1:
        return "give exactly one of all, sha256s, pages and sample" + (f" (not {', '.join(modes)})" if modes else "")
    mode = modes[0]
    if selection.per_page is not None and mode != "pages":
        return "per_page only goes with pages"
    if mode == "pages" and selection.per_page is None:
        return "pages needs per_page"
    if selection.pages is not None and not 1 <= selection.pages[0] <= selection.pages[1]:
        return f"pages: must be 1 <= from <= to, not {selection.pages[0]}..{selection.pages[1]}"
    if selection.seed is not None and mode != "sample":
        return "seed only goes with sample"
    if selection.filtered and mode == "sha256s":
        return "the filters (types, year, month, week) don't go with sha256s"
    if selection.month is not None and selection.year is None:
        return "month only goes with year"
    if selection.week is not None and selection.month is None:
        return "week only goes with month"
    return None
