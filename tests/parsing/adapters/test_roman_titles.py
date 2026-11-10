"""Roman titles (feature 042): the list items numbered with Roman numerals of the Word templates become titles."""

import pytest

from parsing.adapters import promote_roman_titles, roman_level


@pytest.mark.parametrize(
    ("marker", "level"), [("I.", 1), ("IV)", 1), ("III.1.", 2), ("II.3", 2), ("1.", None), ("a)", None), ("•", None)]
)
def test_the_level_comes_from_the_marker(marker: str, level: int | None) -> None:
    assert roman_level(marker) == level


def test_a_roman_list_item_becomes_a_title_and_the_others_stay() -> None:
    doc = pytest.importorskip("docling_core.types.doc")
    document = doc.DoclingDocument(name="plantilla")
    group = document.add_list_group()
    document.add_list_item("Objetivos", marker="I.", parent=group)
    document.add_list_item("Objetivo general", marker="I.1.", parent=group)
    document.add_list_item("Comprender la evaluación", marker="1.", parent=group)
    assert promote_roman_titles(document, doc.SectionHeaderItem) == 2
    found = [(str(item.label.value), getattr(item, "level", None), item.text) for item, _ in document.iterate_items()]
    assert found == [
        ("section_header", 1, "Objetivos"),
        ("section_header", 2, "Objetivo general"),
        ("list_item", None, "Comprender la evaluación"),
    ]
    assert doc.DoclingDocument.model_validate(document.export_to_dict()).texts[0].level == 1
