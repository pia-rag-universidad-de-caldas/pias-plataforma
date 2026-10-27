"""Strategy `section`: the whole section as one chunk, split in consecutive windows if it goes over max_tokens."""

from chunking.models import ChunkPiece, DocumentSection, StrategyParameters

from .base import fit, units
from .tools import Models


def section(section: DocumentSection, parameters: StrategyParameters, models: Models) -> list[ChunkPiece]:
    assert parameters.max_tokens is not None
    return fit(units(section), models.tokens(parameters.tokenizer), parameters.max_tokens)
