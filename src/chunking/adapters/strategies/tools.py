"""The models the strategies (and Docling's HybridChunker) use, loaded once: tokenizers and local embedding models,
downloaded once to TOKENIZER_CACHE / EMBEDDING_CACHE (inside the project) and then read offline. transformers and torch
come with the `chunk` extra (docling-core[chunking]); loaded inside the methods (deferred)."""

import threading
from collections.abc import Callable
from importlib import import_module
from pathlib import Path
from typing import Any

from chunking.config import EMBEDDING_BATCH, EMBEDDING_CACHE, TOKENIZER_CACHE

type Docling = Any  # an object of Docling, transformers or torch (untyped from here)
type Span = tuple[int, int]  # [start, end) of characters in a text

_PROJECT_ROOT = Path(__file__).resolve().parents[4]


def pretrained(kind: Docling, name: str, cache: str) -> Docling:
    """From `cache` without network; downloaded there the first time."""
    try:
        return kind.from_pretrained(name, cache_dir=cache, local_files_only=True)
    except OSError:
        return kind.from_pretrained(name, cache_dir=cache)


class Tokens:
    """Token counting and token windows with a Hugging Face tokenizer (the same count Docling's chunkers use)."""

    def __init__(self, tokenizer: Docling) -> None:
        self.tokenizer = tokenizer

    def count(self, text: str) -> int:
        return len(self.tokenizer.tokenize(text))

    def spans(self, text: str, size: int, overlap: int, fits: Callable[[str], bool]) -> list[Span]:
        """Windows of `size` tokens over `text`, each starting `overlap` tokens before the previous one ended; a
        window that `fits` rejects (re-tokenized at its edges it may count more) shrinks a token at a time."""
        offsets: list[Span] = self.tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)[
            "offset_mapping"
        ]
        spans: list[Span] = []
        start, total = 0, len(offsets)
        while start < total:
            end = min(start + size, total)
            while end - start > 1 and not fits(text[offsets[start][0] : offsets[end - 1][1]]):
                end -= 1
            spans.append((offsets[start][0], offsets[end - 1][1]))
            if end >= total:
                break
            start = max(end - overlap, start + 1)
        return spans


class _Embedder:
    """A local sentence embedding model: mean pooling of the token vectors, normalized (what sentence-transformers
    does for these models), with transformers and torch."""

    def __init__(self, name: str, cache: str) -> None:
        transformers = import_module("transformers")
        self._torch = import_module("torch")
        self._tokenizer = pretrained(transformers.AutoTokenizer, name, cache)
        self._model = pretrained(transformers.AutoModel, name, cache)
        self._model.eval()

    def embed(self, texts: list[str]) -> list[list[float]]:
        torch = self._torch
        vectors: list[list[float]] = []
        for start in range(0, len(texts), EMBEDDING_BATCH):
            encoded = self._tokenizer(
                texts[start : start + EMBEDDING_BATCH], padding=True, truncation=True, return_tensors="pt"
            )
            with torch.no_grad():
                hidden = self._model(**encoded).last_hidden_state
            mask = encoded["attention_mask"].unsqueeze(-1).float()
            mean = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
            vectors += torch.nn.functional.normalize(mean, dim=1).tolist()
        return vectors


class Models:
    """Tokenizers and embedding models by name, each loaded once (thread-safe)."""

    def __init__(self, tokenizer_cache: str | None = None, embedding_cache: str | None = None) -> None:
        self._tokenizer_cache = tokenizer_cache or str(_PROJECT_ROOT / TOKENIZER_CACHE)
        self._embedding_cache = embedding_cache or str(_PROJECT_ROOT / EMBEDDING_CACHE)
        self._lock = threading.Lock()
        self._tokens: dict[str, Tokens] = {}
        self._embedders: dict[str, _Embedder] = {}

    def tokens(self, tokenizer: str) -> Tokens:
        with self._lock:
            if tokenizer not in self._tokens:
                auto = import_module("transformers").AutoTokenizer
                self._tokens[tokenizer] = Tokens(pretrained(auto, tokenizer, self._tokenizer_cache))
            return self._tokens[tokenizer]

    def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        with self._lock:
            if model not in self._embedders:
                self._embedders[model] = _Embedder(model, self._embedding_cache)
            embedder = self._embedders[model]
        return embedder.embed(texts)
