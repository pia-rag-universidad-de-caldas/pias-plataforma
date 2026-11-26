"""Queries of GET /data: safe paths, filters and pages."""

from dataclasses import replace

import pytest

from ingesta.domain import Queries
from ingesta.models import FileFilter, FileRecord

RECORD = FileRecord(
    "2024/01/S/020055/a.pdf",
    "vigentes/pdf/a.pdf",
    2024,
    "01",
    1,
    "S",
    "020055",
    "a.pdf",
    "pdf",
    5000,
    "2024-01-01",
    "2024-01-02",
    "copiado",
    "h1",
    True,
)


@pytest.mark.parametrize(
    ("path", "safe"), [("a/b.pdf", True), ("a..b.pdf", True), ("../a", False), ("a/../b", False), ("/etc/x", False)]
)
def test_is_safe(path: str, safe: bool) -> None:
    assert Queries.is_safe(path) is safe


def test_chunkable_with_hash_takes_the_chunkable_one_if_safe() -> None:
    copy = replace(RECORD, origen="2023/x.pdf")
    assert Queries.chunkable_with_hash([copy, RECORD], {RECORD.origen}) == RECORD
    assert Queries.chunkable_with_hash([copy], {RECORD.origen}) is None
    unsafe = replace(RECORD, destino="../outside.pdf")
    assert Queries.chunkable_with_hash([unsafe], {RECORD.origen}) is None


def test_types_are_normalized() -> None:
    assert Queries.normalized_types([".PDF", "jpeg"]) == frozenset({"pdf", "jpg"})


def test_chunkable_keeps_what_passes_the_filter() -> None:
    other = replace(RECORD, origen="2024/b.docx", tipo="docx", anio=2023)
    found = Queries.chunkable([other, RECORD], {RECORD.origen, other.origen}, FileFilter(frozenset({"pdf"}), 2024))
    assert found == [RECORD]


def test_a_page_says_how_many_there_are_and_holds_what_is_left() -> None:
    page = Queries.paginate([RECORD] * 5, 3, 2)
    assert (page.pages, len(page.files)) == (3, 1)


def test_a_page_past_the_end_is_empty() -> None:
    assert Queries.paginate([RECORD] * 5, 4, 2).files == []
