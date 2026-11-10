"""The text of a previewed DoclingDocument (feature 048): sections by titles, tables by rows, furniture left out."""

from parsing.domain import as_text, preview, sections
from parsing.models import PageCoverage, PreviewSection


def ref(collection: str, index: int) -> dict[str, str]:
    return {"$ref": f"#/{collection}/{index}"}


def text(label: str, value: str, page: int = 1, level: int | None = None, layer: str = "body") -> dict[str, object]:
    item: dict[str, object] = {
        "label": label,
        "text": value,
        "prov": [{"page_no": page}],
        "children": [],
        "content_layer": layer,
    }
    if level is not None:
        item["level"] = level
    return item


PROJECT = text("section_header", "Proyecto", level=2, page=3)
PROJECT["children"] = [ref("texts", 5)]
DOCUMENT: dict[str, object] = {
    "body": {"children": [ref("texts", 0), ref("texts", 1), ref("groups", 0), ref("texts", 4), ref("texts", 6)]},
    "texts": [
        text("title", "Plan del curso"),
        text("page_header", "Universidad", layer="furniture"),
        text("section_header", "Evaluación", level=1),
        text("text", "Dos  parciales\ny un proyecto.", page=2),
        PROJECT,
        text("list_item", "Entrega final", page=3),
        text("section_header", "Bibliografía", level=1, page=4),
    ],
    "groups": [{"label": "section", "children": [ref("texts", 2), ref("texts", 3), ref("tables", 0)]}],
    "tables": [
        {
            "label": "table",
            "prov": [{"page_no": 2}],
            "children": [],
            "data": {"grid": [[{"text": "Parcial"}, {"text": "30 %"}], [{"text": "Proyecto"}, {"text": "Proyecto"}]]},
        }
    ],
}


def test_sections_follow_the_titles_and_leave_furniture_out() -> None:
    assert sections(DOCUMENT) == [
        PreviewSection(["Plan del curso", "Evaluación"], "Dos parciales y un proyecto.\nParcial | 30 %\nProyecto", [2]),
        PreviewSection(["Plan del curso", "Evaluación", "Proyecto"], "Entrega final", [3]),
    ]


def test_the_text_puts_each_section_under_its_titles() -> None:
    found = as_text([PreviewSection(["A", "B"], "uno"), PreviewSection([], "dos")])
    assert found == "A > B\nuno\n\ndos"


def test_a_preview_over_the_page_limit_is_truncated() -> None:
    found = preview("a.pdf", DOCUMENT, PageCoverage(total=40, processed=30), 30)
    assert (found.name, found.pages, found.truncated, len(found.sections)) == ("a.pdf", 40, True, 2)
    assert not preview("a.docx", DOCUMENT, PageCoverage(), 30).truncated


def test_a_reference_that_points_nowhere_is_skipped() -> None:
    broken = {"body": {"children": [ref("texts", 9), {"$ref": "nope"}, ref("texts", 0)]}, "texts": [text("text", "x")]}
    assert sections(broken) == [PreviewSection([], "x", [1])]
