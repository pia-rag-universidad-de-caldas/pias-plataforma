"""What a document's vectors depend on: if any of it changes, they are calculated again."""

import hashlib

from embeddings.config import MODEL_VERSION
from embeddings.models import EmbeddableChunk


def document_fingerprint(model: str, chunks: list[EmbeddableChunk]) -> str:
    base = "\n".join([f"{model}|{MODEL_VERSION}", *(f"{c.id}|{c.text}" for c in chunks)])
    return "sha256:" + hashlib.sha256(base.encode("utf-8")).hexdigest()
