"""Embedder with the local models of config.MODELS, each loaded once (the lru_cache of piaa-rag, safe between
threads). Any failure to load or run a model is the machine's, never the document's."""

import threading
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path

from embeddings.config import EMBEDDING_BATCH, MODEL_CACHE, MODELS, Pooling
from embeddings.models import UpstreamDown

from .text_embedder import TextEmbedder, pretrained

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
MISSING = "torch and transformers are not installed (uv sync --extra embed)"
_MACHINE = (ImportError, OSError, ValueError, RuntimeError, MemoryError)  # what transformers and torch raise


class LocalModels:
    def __init__(self, cache: str | None = None, batch: int = EMBEDDING_BATCH) -> None:
        self._cache = cache or str(_PROJECT_ROOT / MODEL_CACHE)
        self._batch = batch
        self._lock = threading.Lock()  # one model at a time: torch already uses every core
        self._loaded: dict[str, TextEmbedder] = {}
        self._prefixes: dict[str, int | None] = {}  # passage prefix tokens by model (feature 062)

    def available(self) -> bool:
        return find_spec("torch") is not None and find_spec("transformers") is not None

    def _model(self, name: str) -> TextEmbedder:
        if name not in self._loaded:
            if not self.available():
                raise UpstreamDown(MISSING)
            try:
                spec = MODELS.get(name)
                pooling = spec.pooling if spec is not None else Pooling.MEAN
                self._loaded[name] = TextEmbedder(name, self._cache, self._batch, pooling)
            except _MACHINE as error:
                raise UpstreamDown(f"the model {name} can't be loaded: {error}") from error
        return self._loaded[name]

    def embed(self, model: str, texts: list[str], max_tokens: int) -> list[list[float]]:
        with self._lock:
            loaded = self._model(model)
            try:
                return loaded.embed(texts, max_tokens)
            except _MACHINE as error:
                raise UpstreamDown(f"the model {model} failed: {error}") from error

    def tokens(self, model: str, text: str) -> int:
        with self._lock:
            return self._model(model).tokens(text)

    def prefix_tokens(self, model: str) -> int | None:
        """Only the tokenizer is loaded (not the model), once per model; a model without a prefix loads nothing."""
        spec = MODELS.get(model)
        prefix = spec.passage_prefix if spec is not None else ""
        if not prefix:
            return 0
        with self._lock:
            if model not in self._prefixes:
                self._prefixes[model] = self._count_prefix(model, prefix)
            return self._prefixes[model]

    def _count_prefix(self, model: str, prefix: str) -> int | None:
        if not self.available():
            return None
        try:
            tokenizer = pretrained(import_module("transformers").AutoTokenizer, model, self._cache)
            return len(tokenizer(prefix, add_special_tokens=False)["input_ids"])
        except _MACHINE:
            return None
