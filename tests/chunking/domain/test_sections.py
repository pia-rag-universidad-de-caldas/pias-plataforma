"""sections (feature 043): chunks grouped by their heading path, in order of appearance."""

from chunking.domain import sections
from chunking.models import Chunk, Section


def chunk(index: int, *headings: str) -> Chunk:
    return Chunk(index, "t", "t", list(headings), [], 1)


def test_each_heading_path_is_one_section_in_order_of_appearance() -> None:
    found = sections([chunk(0), chunk(1, "A"), chunk(2, "A", "B"), chunk(3, "A"), chunk(4)])
    assert found == [Section(0, []), Section(1, ["A"]), Section(2, ["A", "B"])]


def test_no_chunks_no_sections() -> None:
    assert sections([]) == []
