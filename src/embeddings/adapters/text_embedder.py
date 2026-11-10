"""A local sentence embedding model: the pooling of its token vectors, normalized (what sentence-transformers does for
each model: the mean of the real tokens for MiniLM and e5, the first token for bge-m3's dense vector), with
transformers and torch. They come with the `embed` extra; loaded when it is built. The prefixes a model reads (e5's
`query: `/`passage: `) are the domain's: here the texts arrive as the model must read them."""

from importlib import import_module
from typing import Any

from embeddings.config import Pooling

type Loaded = Any  # an object of transformers or torch (untyped from here)


def pretrained(kind: Loaded, name: str, cache: str) -> Loaded:
    """From `cache` without network; downloaded there the first time."""
    try:
        return kind.from_pretrained(name, cache_dir=cache, local_files_only=True)
    except OSError:
        return kind.from_pretrained(name, cache_dir=cache)


class TextEmbedder:
    def __init__(self, name: str, cache: str, batch: int, pooling: Pooling = Pooling.MEAN) -> None:
        transformers = import_module("transformers")
        self._torch = import_module("torch")
        self._batch = batch
        self._pooling = pooling
        self._tokenizer = pretrained(transformers.AutoTokenizer, name, cache)
        self._model = pretrained(transformers.AutoModel, name, cache)
        self._model.eval()

    def embed(self, texts: list[str], max_length: int) -> list[list[float]]:
        torch = self._torch
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch):
            encoded = self._tokenizer(
                texts[start : start + self._batch],
                padding=True,
                truncation=True,
                max_length=max_length,
                return_tensors="pt",
            )
            with torch.no_grad():
                hidden = self._model(**encoded).last_hidden_state
            vectors += torch.nn.functional.normalize(self._pool(hidden, encoded["attention_mask"]), dim=1).tolist()
        return vectors

    def _pool(self, hidden: Loaded, attention: Loaded) -> Loaded:
        """One vector per text: the first token's ([CLS]) or the mean of the real ones (padding left out)."""
        if self._pooling is Pooling.CLS:
            return hidden[:, 0]
        mask = attention.unsqueeze(-1).float()
        return (hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)

    def tokens(self, text: str) -> int:
        """With the model's special tokens, as it reads them."""
        return len(self._tokenizer(text, add_special_tokens=True)["input_ids"])
