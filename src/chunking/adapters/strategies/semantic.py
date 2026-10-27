"""Strategy `semantic`: consecutive elements (those over max_tokens first split in windows) are joined while the
embedding similarity of each with the previous one stays >= similarity_threshold and the chunk stays within
max_tokens. Embeddings come from a local model (Models.embed)."""

from chunking.models import ChunkPiece, DocumentSection, StrategyParameters

from .base import Unit, distinct, fit, units
from .tools import Models


def similarity(a: list[float], b: list[float]) -> float:
    """Cosine of two normalized vectors."""
    return sum(x * y for x, y in zip(a, b, strict=True))


def semantic(section: DocumentSection, parameters: StrategyParameters, models: Models) -> list[ChunkPiece]:
    assert parameters.max_tokens is not None and parameters.embedding_model is not None
    assert parameters.similarity_threshold is not None
    tokens, limit = models.tokens(parameters.tokenizer), parameters.max_tokens
    found = [
        Unit(p.text, p.headings, p.pages, unit.kind) for unit in units(section) for p in fit([unit], tokens, limit)
    ]
    if not found:
        return []
    vectors = models.embed(parameters.embedding_model, [u.text for u in found])
    groups: list[list[Unit]] = [[found[0]]]
    for i in range(1, len(found)):
        joined = "\n".join([*(u.text for u in groups[-1]), found[i].text])
        if similarity(vectors[i - 1], vectors[i]) >= parameters.similarity_threshold and tokens.count(joined) <= limit:
            groups[-1].append(found[i])
        else:
            groups.append([found[i]])
    pieces: list[ChunkPiece] = []
    for group in groups:
        text = "\n".join(u.text for u in group)
        pages = distinct(p for u in group for p in u.pages)
        pieces.append(ChunkPiece(text, group[0].headings, pages, tokens.count(text)))
    return pieces
