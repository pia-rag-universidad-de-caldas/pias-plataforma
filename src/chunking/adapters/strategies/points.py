"""Strategy `points`: one chunk per point — each list item, and each numeral or bullet inside a paragraph (PDFs often
bring a list as one paragraph: "OBJETIVOS GENERALES: ü Discutir ... ü Reflexionar ..."). The text that isn't a
point goes by paragraphs; tables, one chunk each. A point over max_tokens is split. A short lead-in ending in ":"
("Específicos:") is a heading of the points that follow, not a chunk."""

import re

from chunking.models import ChunkPiece, DocumentSection, ElementKind, StrategyParameters

from .base import Unit, fit, units
from .tools import Models

# Where a point starts inside a paragraph: a bullet glyph ("ü" is how Wingdings' check mark comes out of many PDFs) or
# a numeral ("1.", "2)", "a)") followed by a capital letter.
_BULLET = r"[•●▪◦■□➢►✓✔ü]\s*"
_NUMERAL = r"(?:\d{1,2}|[a-z])[.)]\s+(?=[A-ZÁÉÍÓÚÑ¿¡])"
_POINT = re.compile(rf"(?:^|(?<=\s))(?:{_BULLET}(?=\S)|{_NUMERAL})")
_LEAD_IN = 120  # characters: a lead-in ending in ":" up to this long is a heading


def split_points(text: str) -> tuple[str, list[str]]:
    """(lead-in, points) of a paragraph; no points → ("", [text])."""
    starts = [m.start() for m in _POINT.finditer(text)]
    if not starts:
        return "", [text]
    pieces = [text[a:b] for a, b in zip(starts, [*starts[1:], len(text)], strict=True)]
    points = [re.sub(rf"^{_BULLET}", "", p).strip() for p in pieces]
    return text[: starts[0]].strip(), [p for p in points if p]


def points(section: DocumentSection, parameters: StrategyParameters, models: Models) -> list[ChunkPiece]:
    assert parameters.max_tokens is not None
    tokens, limit = models.tokens(parameters.tokenizer), parameters.max_tokens
    found: list[Unit] = []
    lead: str | None = None
    for unit in units(section):
        if unit.kind == ElementKind.SUBTITLE:
            lead = None
            continue
        if unit.kind != ElementKind.PARAGRAPH:
            found.append(Unit(unit.text, [*unit.headings, lead] if lead else unit.headings, unit.pages, unit.kind))
            continue
        intro, parts = split_points(unit.text)
        if not intro and len(parts) == 1 and parts[0].endswith(":") and len(parts[0]) <= _LEAD_IN:
            lead = parts[0].rstrip(":").strip()  # a lead-in alone: heads the next points
            continue
        if intro and intro.endswith(":") and len(intro) <= _LEAD_IN:
            lead = intro.rstrip(":").strip()
        elif intro:
            found.append(Unit(intro, unit.headings, unit.pages, unit.kind))
        headings = [*unit.headings, lead] if lead else unit.headings
        found += [Unit(p, headings, unit.pages, ElementKind.LIST_ITEM) for p in parts]
    return [piece for unit in found for piece in fit([unit], tokens, limit)]
