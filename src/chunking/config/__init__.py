"""Chunking settings: what Docling's chunking can and can't change (docling.py) and where data is (settings.py)."""

from common.config import DATA_PATH, MAX_PER_PAGE, PER_PAGE

from .docling import (
    CHUNKERS,
    CHUNKING_DEFAULT,
    CHUNKING_FIXED,
    CHUNKING_VERSION,
    MAX_TOKENS_RANGE,
    TOKENIZERS,
    ChunkingDefault,
    ChunkingFixed,
)
from .settings import GRAPH_PAGE_SIZE, RUN_TIMEOUT, SELF_URL, TOKENIZER_CACHE

__all__ = [
    "CHUNKERS",
    "CHUNKING_DEFAULT",
    "CHUNKING_FIXED",
    "CHUNKING_VERSION",
    "DATA_PATH",
    "GRAPH_PAGE_SIZE",
    "MAX_PER_PAGE",
    "MAX_TOKENS_RANGE",
    "PER_PAGE",
    "RUN_TIMEOUT",
    "SELF_URL",
    "TOKENIZERS",
    "TOKENIZER_CACHE",
    "ChunkingDefault",
    "ChunkingFixed",
]
