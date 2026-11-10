"""A model's official vectors (feature 055): how many documents have them, and dropping them once another model is
active. Changing models without cutting the chat: POST /runs with `model` embeds next to the active one, PUT /config
makes it active, and then this drops the old one's property, index and fingerprints."""

from itertools import batched

from embeddings.config import FINGERPRINT_BATCH, MODELS
from embeddings.models import ChunkSource, DroppedVectors, EmbeddingConfig, GraphLabel, VectorSink

from .batches import unfingerprinted_batch
from .indexes import fingerprint_key, vector_index
from .limits import token_limit


class ActiveModel(Exception):
    """The active model's vectors are what the chat searches: 409."""


def documents_per_model(source: ChunkSource) -> dict[str, int]:
    """Served model → how many official JSON have its fingerprint (its vectors were calculated)."""
    counts = source.fingerprint_counts()
    return {model: counts.get(fingerprint_key(model), 0) for model in MODELS}


def drop_vectors(source: ChunkSource, sink: VectorSink, model: str, active: EmbeddingConfig) -> DroppedVectors:
    """Removes `model`'s fingerprints from the JSON first (so a later run embeds again, even if what follows fails),
    then its FRAGMENTOS index and property. InvalidLimit (422) if it isn't served; ActiveModel (409) if it is the
    active one."""
    token_limit(model, None)
    if model == active.model:
        raise ActiveModel(f"{model} is the active model: the chat searches its vectors (PUT /config another first)")
    sha256s = source.with_fingerprint(fingerprint_key(model))
    for group in batched(sha256s, FINGERPRINT_BATCH):
        sink.save(unfingerprinted_batch(group, model))
    index = vector_index(GraphLabel.FRAGMENTOS, model)
    return DroppedVectors(model, index.name, sink.drop_index(index.name, True), len(sha256s))
