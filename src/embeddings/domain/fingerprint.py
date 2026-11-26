"""What a document's vectors depend on: if any of it changes, they are calculated again."""

import hashlib

from embeddings.config import MODEL_VERSION
from embeddings.models import EmbeddableChunk


def document_fingerprint(model: str, chunks: list[EmbeddableChunk], heading: str = "") -> str:
    """`heading`: what goes in front of every chunk (the course, feature 057); without one, the fingerprint is the
    one from before it, so a document whose course can't be read isn't embedded again for nothing."""
    lines = [
        f"{model}|{MODEL_VERSION}",
        *([f"heading|{heading}"] if heading else []),
        *(f"{c.id}|{c.text}" for c in chunks),
    ]
    base = "\n".join(lines)
    return "sha256:" + hashlib.sha256(base.encode("utf-8")).hexdigest()
