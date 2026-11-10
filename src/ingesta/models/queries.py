"""API queries on the memory: the filters it receives and the page it returns."""

from dataclasses import dataclass

from .entities import FileRecord


@dataclass(frozen=True)
class FileFilter:
    """Conditions a file must meet, all at once; an empty field doesn't filter."""

    types: frozenset[str] = frozenset()  # normalized extensions; any of them
    year: int | None = None
    month: int | None = None  # mes_num, 1-12
    week: str | None = None
    code: str | None = None


@dataclass(frozen=True)
class FilePage:
    page: int  # from 1
    per_page: int
    total: int  # files that meet the filter, across all pages
    pages: int
    files: list[FileRecord]
