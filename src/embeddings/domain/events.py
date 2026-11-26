"""What a run tells whoever runs it, as it goes (the registry, the log): the domain itself never logs."""

from collections.abc import Callable
from dataclasses import dataclass

from embeddings.config import MODELS
from embeddings.models import DocumentError, DocumentFailure, EmbeddableChunk, Embedder, RunProgress

from .prefixes import passages


def _ignore(_: object) -> None:
    pass


@dataclass(frozen=True)
class RunEvents:
    progress: Callable[[RunProgress], None] = _ignore  # after each document
    failure: Callable[[DocumentFailure], None] = _ignore  # a document failed, or wasn't in data
    embedded: Callable[[str], None] = _ignore  # a document's chunks have vectors now (or already had them)
    listed: Callable[[list[str]], None] = _ignore  # the documents a run without sha256s took (feature 057)
    stop: Callable[[], bool] = lambda: False  # asked before each document: True ends the run there (feature 056)


def check_lengths(embedder: Embedder, model: str, limit: int, chunks: list[EmbeddableChunk]) -> None:
    """A chunk longer than `limit` (with the model's passage prefix, which it reads too) makes its document fail
    (DocumentError) before anything is calculated: it is never cut without saying (piaa-rag only warned)."""
    texts = passages(model, [c.text for c in chunks])
    long = [c.id for c, text in zip(chunks, texts, strict=True) if embedder.tokens(model, text) > limit]
    if long:
        raise DocumentError(f"{len(long)} chunks go over {limit} tokens of {model}, e.g. {long[0]}")


HEADING_TOKENS = 48  # what a heading may add to the limit (identity.HEADING_CHARS characters, ~40 tokens)


def vectors(
    embedder: Embedder, model: str, limit: int, chunks: list[EmbeddableChunk], heading: str = ""
) -> list[list[float]]:
    """The chunks' vectors, once their lengths are checked. `heading` (the course, feature 057) goes in front of
    each one: it doesn't count in the chunk's limit (chunking cut the chunks to it), so the model reads up to
    HEADING_TOKENS more, never over its positions."""
    check_lengths(embedder, model, limit, chunks)
    if not chunks:
        return []
    reads = min(limit + HEADING_TOKENS, MODELS[model].max_tokens) if heading else limit
    return embedder.embed(model, passages(model, [heading + c.text for c in chunks]), reads)
