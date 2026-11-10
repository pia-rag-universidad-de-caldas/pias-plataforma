"""An embedding model: mean pooling of the tokens, normalized (moved from chunking's `semantic` strategy, feature
046), with each call's own limit."""

from types import SimpleNamespace

import pytest

from embeddings.adapters import text_embedder
from embeddings.adapters.text_embedder import TextEmbedder
from embeddings.config import Pooling


def fake_transformers(monkeypatch: pytest.MonkeyPatch, asked: list[dict[str, object]]) -> None:
    torch = pytest.importorskip("torch")

    class Tokenizer:
        def __call__(self, batch: list[str], **options: object) -> dict[str, object]:
            asked.append(options)
            return {"attention_mask": torch.tensor([[1, 1, 0]] * len(batch))}

    class Model:
        def eval(self) -> None:
            pass

        def __call__(self, **_: object) -> SimpleNamespace:
            return SimpleNamespace(last_hidden_state=torch.tensor([[[3.0, 0.0], [3.0, 8.0], [99.0, 99.0]]]))

    transformers = SimpleNamespace(
        AutoTokenizer=SimpleNamespace(from_pretrained=lambda *_, **__: Tokenizer()),
        AutoModel=SimpleNamespace(from_pretrained=lambda *_, **__: Model()),
    )
    monkeypatch.setattr(text_embedder, "import_module", lambda name: transformers if name == "transformers" else torch)


def test_the_vectors_are_the_mean_of_the_real_tokens_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_transformers(monkeypatch, [])
    [vector] = TextEmbedder("m", "/e", 8).embed(["a"], 128)
    assert vector == pytest.approx([0.6, 0.8])  # the mean is (3, 4); the third token is padding


def test_each_call_gives_its_own_limit_to_the_tokenizer(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[dict[str, object]] = []
    fake_transformers(monkeypatch, asked)
    model = TextEmbedder("m", "/e", 8)
    model.embed(["a"], 128)
    model.embed(["a"], 300)
    assert [a["max_length"] for a in asked] == [128, 300]


def test_a_cls_model_takes_the_first_token_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    """bge-m3's dense vector (feature 055): its [CLS], not the mean."""
    fake_transformers(monkeypatch, [])
    [vector] = TextEmbedder("m", "/e", 8, Pooling.CLS).embed(["a"], 128)
    assert vector == pytest.approx([1.0, 0.0])  # the first token is (3, 0)
