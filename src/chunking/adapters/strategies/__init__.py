"""Chunking strategies (feature 025), one per file, over the sections of a ConvertedDocument (no Docling).
SectionStrategies implements the SectionChunker port: it picks the strategy and lends it the models."""

from importlib.util import find_spec

from chunking.models import ChunkingStrategy, ChunkPiece, ConversionError, DocumentSection, StrategyParameters

from .base import Strategy
from .element import element
from .fixed import fixed
from .hybrid import hybrid
from .page import page
from .points import points
from .section import section
from .semantic import semantic
from .tools import Docling, Models, Tokens

STRATEGIES: dict[ChunkingStrategy, Strategy] = {
    ChunkingStrategy.HYBRID: hybrid,
    ChunkingStrategy.ELEMENT: element,
    ChunkingStrategy.SECTION: section,
    ChunkingStrategy.PAGE: page,
    ChunkingStrategy.FIXED: fixed,
    ChunkingStrategy.POINTS: points,
    ChunkingStrategy.SEMANTIC: semantic,
}

MISSING = "transformers is not installed (it comes with the chunk extra): uv sync --extra chunk"


class SectionStrategies:
    def __init__(self, models: Models) -> None:
        self._models = models

    def available(self) -> bool:
        return find_spec("transformers") is not None and find_spec("torch") is not None

    def chunk(self, section: DocumentSection, parameters: StrategyParameters) -> list[ChunkPiece]:
        if not self.available():
            raise ConversionError(MISSING)
        try:
            pieces = STRATEGIES[parameters.strategy](section, parameters, self._models)
        except ConversionError:
            raise
        except Exception as e:  # a model that can't be downloaded or loaded...
            raise ConversionError(f"{type(e).__name__}: {e}".strip()) from e
        return [p for p in pieces if p.tokens > 0 and p.text.strip()]  # nothing left once tokenized: not a chunk


__all__ = ["STRATEGIES", "Docling", "Models", "SectionStrategies", "Strategy", "Tokens"]
