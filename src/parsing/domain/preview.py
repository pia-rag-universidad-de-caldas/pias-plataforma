"""The text of a DoclingDocument (as export_to_dict gives it) for POST /preview (feature 048): its body in reading
order, cut in sections by its titles. Without Docling: the exported document is a tree of `$ref`s from `body` to the
items of `texts`, `groups`, `tables` and `pictures`, and that is all this reads.

    title / section_header (level n)  → a new section, under the titles of the levels above it
    text, list items, captions...     → a line of the section
    table                             → one line per row, its cells joined with " | "
    furniture (headers, footers)      → left out, as chunking does
"""

from collections.abc import Iterator, Mapping, Sequence

from parsing.models import PageCoverage, PreviewDocument, PreviewSection

type Item = Mapping[str, object]

_HEADINGS = {"title", "section_header"}
_BODY = "body"
_CELL = " | "


def _mapping(value: object) -> Item | None:
    return value if isinstance(value, Mapping) else None


def _list(value: object) -> Sequence[object]:
    return value if isinstance(value, list) else []


def _resolve(document: Item, ref: object) -> Item | None:
    """`{"$ref": "#/texts/3"}` → the item it points to; None if it doesn't point anywhere."""
    found = _mapping(ref)
    path = found.get("$ref") if found else None
    if not isinstance(path, str) or not path.startswith("#/"):
        return None
    collection, _, index = path[2:].partition("/")
    items = _list(document.get(collection))
    if not index.isdigit() or int(index) >= len(items):
        return None
    return _mapping(items[int(index)])


def _walk(document: Item, item: Item, seen: set[int]) -> Iterator[Item]:
    """The items under `item`, depth first: the reading order."""
    for ref in _list(item.get("children")):
        child = _resolve(document, ref)
        if child is None or id(child) in seen:
            continue
        seen.add(id(child))
        if child.get("content_layer", _BODY) == _BODY:
            yield child
            yield from _walk(document, child, seen)


def _pages(item: Item) -> set[int]:
    found: set[int] = set()
    for prov in _list(item.get("prov")):
        page = _mapping(prov)
        number = page.get("page_no") if page else None
        if isinstance(number, int):
            found.add(number)
    return found


def _rows(table: Item) -> list[str]:
    data = _mapping(table.get("data")) or {}
    rows: list[str] = []
    for row in _list(data.get("grid")):
        cells: list[str] = []
        for cell in _list(row):
            text = _mapping(cell)
            value = " ".join(str(text.get("text") or "").split()) if text else ""
            if value and (not cells or cells[-1] != value):  # a merged cell repeats in the grid: once
                cells.append(value)
        if cells:
            rows.append(_CELL.join(cells))
    return rows


def _level(item: Item) -> int:
    if item.get("label") == "title":
        return 0
    level = item.get("level")
    return level if isinstance(level, int) and level > 0 else 1


def sections(document: Mapping[str, object]) -> list[PreviewSection]:
    """The sections of the document in reading order; a section without text (two titles in a row) is left out."""
    found: list[PreviewSection] = []
    titles: dict[int, str] = {}
    lines: list[str] = []
    pages: set[int] = set()

    def close() -> None:
        if lines:
            found.append(PreviewSection([titles[k] for k in sorted(titles)], "\n".join(lines), sorted(pages)))
        lines.clear()
        pages.clear()

    body = _mapping(document.get("body")) or {}
    for item in _walk(document, body, set()):
        label = item.get("label")
        if label == "table":
            lines.extend(_rows(item))
            pages.update(_pages(item))
            continue
        text = " ".join(str(item.get("text") or "").split())
        if not text:
            continue
        if label in _HEADINGS:
            close()
            level = _level(item)
            titles = {k: v for k, v in titles.items() if k < level}
            titles[level] = text
            continue
        lines.append(text)
        pages.update(_pages(item))
    close()
    return found


def as_text(found: Sequence[PreviewSection]) -> str:
    """The sections one after the other, each one under its titles."""
    blocks = []
    for section in found:
        heading = " > ".join(section.headings)
        blocks.append(f"{heading}\n{section.text}" if heading else section.text)
    return "\n\n".join(blocks)


def preview(name: str, document: Mapping[str, object], coverage: PageCoverage, max_pages: int) -> PreviewDocument:
    found = sections(document)
    truncated = coverage.total > max_pages or not coverage.complete
    return PreviewDocument(name, coverage.total, truncated, as_text(found), found)
