"""LocalModels: each model loaded once; a model that can't be loaded is the machine's failure."""

import pytest

from embeddings.adapters import local_models
from embeddings.adapters.local_models import LocalModels
from embeddings.config import Pooling
from embeddings.models import UpstreamDown


class Loaded:
    built = 0
    pooling = Pooling.MEAN

    def __init__(self, name: str, cache: str, batch: int, pooling: Pooling = Pooling.MEAN) -> None:
        Loaded.built += 1
        Loaded.pooling = pooling

    def embed(self, texts: list[str], max_length: int) -> list[list[float]]:
        return [[1.0] for _ in texts]

    def tokens(self, text: str) -> int:
        return 3


def test_a_model_is_loaded_once(monkeypatch: pytest.MonkeyPatch) -> None:
    Loaded.built = 0
    monkeypatch.setattr(local_models, "TextEmbedder", Loaded)
    monkeypatch.setattr(LocalModels, "available", lambda _: True)
    models = LocalModels("/cache")
    models.embed("m", ["a"], 128)
    models.tokens("m", "a")
    assert Loaded.built == 1


def test_a_model_that_cannot_be_loaded_is_upstream_down(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(name: str, cache: str, batch: int, pooling: Pooling) -> Loaded:
        raise OSError("no such model in the hub")

    monkeypatch.setattr(local_models, "TextEmbedder", broken)
    monkeypatch.setattr(LocalModels, "available", lambda _: True)
    with pytest.raises(UpstreamDown, match="can't be loaded"):
        LocalModels("/cache").tokens("m", "a")


def test_without_torch_it_says_how_to_install_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(LocalModels, "available", lambda _: False)
    with pytest.raises(UpstreamDown, match="--extra embed"):
        LocalModels("/cache").embed("m", ["a"], 128)


def test_each_model_is_loaded_with_its_pooling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(local_models, "TextEmbedder", Loaded)
    monkeypatch.setattr(LocalModels, "available", lambda _: True)
    LocalModels("/cache").tokens("BAAI/bge-m3", "a")
    assert Loaded.pooling is Pooling.CLS


class Tokenizer:
    """transformers' AutoTokenizer: one token per character of the text (no special tokens asked for)."""

    loaded = 0

    @classmethod
    def from_pretrained(cls, name: str, cache_dir: str, local_files_only: bool = False) -> "Tokenizer":
        cls.loaded += 1
        return cls()

    def __call__(self, text: str, add_special_tokens: bool = True) -> dict[str, list[int]]:
        return {"input_ids": list(range(len(text) + (2 if add_special_tokens else 0)))}


class Transformers:
    AutoTokenizer = Tokenizer


def test_a_passage_prefix_is_counted_with_only_the_tokenizer_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Feature 062: the model itself isn't loaded (TextEmbedder never built), and the count is kept."""
    Loaded.built, Tokenizer.loaded = 0, 0
    monkeypatch.setattr(local_models, "TextEmbedder", Loaded)
    monkeypatch.setattr(local_models, "import_module", lambda name: Transformers)
    monkeypatch.setattr(LocalModels, "available", lambda _: True)
    models = LocalModels("/cache")
    assert [models.prefix_tokens("intfloat/multilingual-e5-base") for _ in range(2)] == [len("passage: ")] * 2
    assert (Tokenizer.loaded, Loaded.built) == (1, 0)


def test_a_model_without_a_prefix_loads_nothing_and_without_the_extra_a_prefix_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(LocalModels, "available", lambda _: False)
    models = LocalModels("/cache")
    assert models.prefix_tokens("BAAI/bge-m3") == 0
    assert models.prefix_tokens("intfloat/multilingual-e5-base") is None
