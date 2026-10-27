"""Strategy `fixed`: windows of max_tokens tokens with overlap_tokens of overlap over the text of the section,
ignoring its elements (the classic RAG baseline)."""

from chunking.models import ChunkPiece, DocumentSection, StrategyParameters

from .base import fit, units
from .tools import Models


def fixed(section: DocumentSection, parameters: StrategyParameters, models: Models) -> list[ChunkPiece]:
    assert parameters.max_tokens is not None and parameters.overlap_tokens is not None
    tokens = models.tokens(parameters.tokenizer)
    return fit(units(section), tokens, parameters.max_tokens, overlap=parameters.overlap_tokens)
