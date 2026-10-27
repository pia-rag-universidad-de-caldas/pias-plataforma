"""Strategy `element`: one chunk per element (paragraph, list item, table); max_tokens doesn't apply (an element is
never split). Subtitles are headings, not chunks."""

from chunking.models import ChunkPiece, DocumentSection, ElementKind, StrategyParameters

from .base import units
from .tools import Models


def element(section: DocumentSection, parameters: StrategyParameters, models: Models) -> list[ChunkPiece]:
    tokens = models.tokens(parameters.tokenizer)
    return [
        ChunkPiece(u.text, u.headings, u.pages, tokens.count(u.text))
        for u in units(section)
        if u.kind != ElementKind.SUBTITLE
    ]
