"""Values of the embeddings module and the location of data, the only module it talks to."""

from common.config import DATA_PATH, MAX_PER_PAGE, PER_PAGE

from .settings import (
    ACTIVE_CONFIG_ID,
    CHUNKED,
    CHUNKED_KEY,
    DEFAULT_MODEL,
    EMBEDDING_BATCH,
    FINGERPRINT_BATCH,
    FINISHED_EXPERIMENT,
    MAX_TEXT,
    MAX_TEXTS,
    MAX_WAITING,
    MODEL_CACHE,
    MODEL_VERSION,
    MODELS,
    RUN_TIMEOUT,
    ModelSpec,
    Pooling,
)

__all__ = [
    "ACTIVE_CONFIG_ID",
    "CHUNKED",
    "CHUNKED_KEY",
    "DATA_PATH",
    "DEFAULT_MODEL",
    "EMBEDDING_BATCH",
    "FINGERPRINT_BATCH",
    "FINISHED_EXPERIMENT",
    "MAX_PER_PAGE",
    "MAX_TEXT",
    "MAX_TEXTS",
    "MAX_WAITING",
    "MODELS",
    "MODEL_CACHE",
    "MODEL_VERSION",
    "PER_PAGE",
    "RUN_TIMEOUT",
    "ModelSpec",
    "Pooling",
]
