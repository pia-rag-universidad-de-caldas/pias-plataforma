"""What every strategy shares (feature 025): the units of a section, token windows and how a group of units becomes
chunks. Strategies work on the sections of a ConvertedDocument: no Docling here."""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from chunking.models import ChunkPiece, DocumentSection, ElementKind, StrategyParameters

from .tools import Models, Span, Tokens

SEPARATOR = "\n"


@dataclass(frozen=True)
class Unit:
    """One element of a section, with the headings it falls under (the section title and its current subtitle)."""

    text: str
    headings: list[str]
    pages: list[int]
    kind: ElementKind


def units(section: DocumentSection) -> list[Unit]:
    base = [section.title] if section.title else []
    subtitle: str | None = None
    found: list[Unit] = []
    for element in section.elements:
        if element.kind == ElementKind.SUBTITLE:
            subtitle = element.text
            found.append(Unit(element.text, [*base, element.text], element.pages, element.kind))
            continue
        text = element.text
        if element.marker and any(c.isalnum() for c in element.marker):  # "1.", "a)": part of the point
            text = f"{element.marker} {text}"
        found.append(Unit(text, [*base, subtitle] if subtitle else base, element.pages, element.kind))
    return found


def distinct(values: Iterable[int]) -> list[int]:
    return sorted(set(values))


def located(found: list[Unit]) -> tuple[str, list[tuple[Span, Unit]]]:
    """The units joined in one text, and where each one is in it."""
    spans: list[tuple[Span, Unit]] = []
    position = 0
    for unit in found:
        spans.append(((position, position + len(unit.text)), unit))
        position += len(unit.text) + len(SEPARATOR)
    return SEPARATOR.join(u.text for u in found), spans


def covered(spans: list[tuple[Span, Unit]], span: Span) -> list[Unit]:
    """The units a span of the joined text touches."""
    start, end = span
    return [unit for (a, b), unit in spans if a < end and b > start]


def fit(
    group: list[Unit], tokens: Tokens, max_tokens: int, overlap: int = 0, page: int | None = None
) -> list[ChunkPiece]:
    """The group as one chunk if it fits max_tokens; else consecutive windows of max_tokens (with `overlap`). Each
    piece hangs from the headings of its first unit and says the pages of the units it covers (or only `page`)."""
    if not group:
        return []
    text, spans = located(group)
    whole = tokens.count(text)
    windows = (
        [(0, len(text))]
        if whole <= max_tokens and not overlap
        else tokens.spans(text, max_tokens, overlap, lambda piece: tokens.count(piece) <= max_tokens)
    )
    pieces: list[ChunkPiece] = []
    for span in windows:
        inside = covered(spans, span) or group[:1]
        piece = text[span[0] : span[1]]
        pages = [page] if page is not None else distinct(p for u in inside for p in u.pages)
        pieces.append(
            ChunkPiece(piece, inside[0].headings, pages, whole if span == (0, len(text)) else tokens.count(piece))
        )
    return pieces


class Strategy(Protocol):
    def __call__(
        self, section: DocumentSection, parameters: StrategyParameters, models: Models
    ) -> list[ChunkPiece]: ...
