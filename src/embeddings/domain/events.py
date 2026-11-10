"""What a run tells whoever runs it, as it goes (the registry, the log): the domain itself never logs."""

from collections.abc import Callable
from dataclasses import dataclass

from embeddings.models import DocumentError, DocumentFailure, EmbeddableChunk, Embedder, RunProgress

from .prefixes import passages


def _ignore(_: object) -> None:
    pass


@dataclass(frozen=True)
class RunEvents:
    progress: Callable[[RunProgress], None] = _ignore  # after each document
    failure: Callable[[DocumentFailure], None] = _ignore  # a document failed, or wasn't in data
    embedded: Callable[[str], None] = _ignore  # a document's chunks have vectors now (or already had them)


def check_lengths(embedder: Embedder, model: str, limit: int, chunks: list[EmbeddableChunk]) -> None:
    """A chunk longer than `limit` (with the model's passage prefix, which it reads too) makes its document fail
    (DocumentError) before anything is calculated: it is never cut without saying (piaa-rag only warned)."""
    texts = passages(model, [c.text for c in chunks])
    long = [c.id for c, text in zip(chunks, texts, strict=True) if embedder.tokens(model, text) > limit]
    if long:
        raise DocumentError(f"{len(long)} chunks go over {limit} tokens of {model}, e.g. {long[0]}")


def vectors(embedder: Embedder, model: str, limit: int, chunks: list[EmbeddableChunk]) -> list[list[float]]:
    """The chunks' vectors, once their lengths are checked."""
    check_lengths(embedder, model, limit, chunks)
    return embedder.embed(model, passages(model, [c.text for c in chunks]), limit) if chunks else []
