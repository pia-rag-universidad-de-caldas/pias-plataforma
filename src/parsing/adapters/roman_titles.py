"""Roman titles (feature 042): in the Word templates the titles are list items numbered with Roman numerals ("I.",
"IV)" level 1; "III.1." level 2). They become titles in the DoclingDocument before it is stored, so that every chunker
puts them in front of their chunks. Docling's own heading hierarchy only reads PDFs."""

import re
from typing import Any

type Docling = Any  # Docling is untyped from here on (it is imported deferred)

_LEVEL_1 = re.compile(r"^[IVXLC]+[.)]$")
_LEVEL_2 = re.compile(r"^[IVXLC]+[.)]\d+[.)]?$")


def roman_level(marker: str) -> int | None:
    marker = marker.strip()
    if _LEVEL_1.match(marker):
        return 1
    if _LEVEL_2.match(marker):
        return 2
    return None


def _text(document: Docling, item: Docling) -> str:
    own = str(getattr(item, "text", "") or "").strip()
    if own:
        return own
    texts = [str(getattr(i, "text", "") or "") for i, _ in document.iterate_items(root=item, with_groups=False)]
    return " ".join(t.strip() for t in texts if t.strip())


def promote_roman_titles(document: Docling, header_type: Docling) -> int:
    """Turns each Roman-numbered list item into a title of its level, in place (same reference, so whatever points to
    it still does). `header_type`: docling_core's SectionHeaderItem. How many it turned."""
    turned = 0
    for index, item in enumerate(document.texts):
        if str(getattr(item.label, "value", item.label)) != "list_item":
            continue
        level = roman_level(str(getattr(item, "marker", "") or ""))
        text = _text(document, item) if level else ""
        if not level or not text:
            continue
        fields = item.model_dump()
        for key in ("marker", "enumerated", "first_list_item", "label"):
            fields.pop(key, None)
        fields.update(text=text, orig=text, level=level)
        document.texts[index] = header_type.model_validate(fields)
        turned += 1
    return turned
