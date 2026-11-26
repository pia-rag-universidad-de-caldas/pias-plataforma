"""pairing with fit (feature 062): several embedding models over the same chunks, each within its passage budget
(its limit minus its special tokens and its passage prefix)."""

import pytest

from pipeline.domain import pair
from pipeline.domain.pairing import budgets, chosen_models, chunk_fit, embeddings_limit, uncovered
from pipeline.models import EmbeddingModel, InvalidRequest, JsonObject

MINILM = EmbeddingModel("minilm", default_tokens=128, max_tokens=512, default=True)
E5 = EmbeddingModel("e5", 512, 512, False, passage_budget=507, default_passage_budget=507, official_passage_budget=459)


def test_the_laboratory_counts_the_prefix_of_e5_in_its_budget() -> None:
    fitted = pair({"embeddings": {"model": "e5"}}, [E5])
    assert fitted.chunking["max_tokens"] == 507 and fitted.embeddings["max_tokens"] == 512
    with pytest.raises(InvalidRequest, match="can't pass 507"):
        pair({"chunking": {"max_tokens": 508}, "embeddings": {"model": "e5"}}, [E5])


def test_without_budgets_a_model_falls_back_to_its_limit_minus_the_special_tokens() -> None:
    assert (MINILM.budget, MINILM.default_budget, MINILM.official_budget, MINILM.overhead) == (510, 126, 510, 2)


def test_a_new_experiment_fits_every_model_with_its_default_budget_under_the_top() -> None:
    chunking = chunk_fit({"chunker": "hybrid", "max_tokens": 200}, [MINILM, E5])
    assert chunking == {
        "chunker": "hybrid",
        "fit": [{"tokenizer": "minilm", "max_tokens": 126}, {"tokenizer": "e5", "max_tokens": 200}],
    }


def test_without_a_top_each_model_gets_its_default_budget() -> None:
    assert chunk_fit({}, [E5])["fit"] == [{"tokenizer": "e5", "max_tokens": 507}]


def test_without_models_or_with_another_chunker_the_chunking_goes_as_it_is() -> None:
    assert chunk_fit({"max_tokens": 50}, []) == {"max_tokens": 50}
    assert chunk_fit({"chunker": "page"}, [E5]) == {"chunker": "page"}


@pytest.mark.parametrize("key", ["tokenizer", "fit"])
def test_a_tokenizer_or_fit_with_models_is_refused(key: str) -> None:
    with pytest.raises(InvalidRequest, match=f"chunking.{key}"):
        chunk_fit({key: "x"}, [E5])


def test_a_top_that_isnt_a_positive_integer_is_refused() -> None:
    with pytest.raises(InvalidRequest, match="positive integer"):
        chunk_fit({"max_tokens": 0}, [E5])


def test_chunks_cover_a_model_counted_with_its_tokenizer_within_its_budget() -> None:
    fit: JsonObject = {"fit": [{"tokenizer": "e5", "max_tokens": 500}]}
    assert budgets(fit) == {"e5": 500} and uncovered(fit, [E5]) == []
    assert uncovered(fit, [E5], official=True) == ["e5 doesn't fit: its chunks may have 500 tokens and it takes 459"]


def test_chunks_counted_with_another_tokenizer_or_without_top_dont_cover_it() -> None:
    assert uncovered({"tokenizer": "e5", "max_tokens": 100}, [MINILM])[0].startswith("minilm doesn't fit")
    assert "no top" in uncovered({"chunker": "page"}, [E5])[0]


def test_an_embeddings_experiment_takes_the_chunks_top_plus_the_models_overhead() -> None:
    assert embeddings_limit({"fit": [{"tokenizer": "e5", "max_tokens": 300}]}, E5) == 305
    assert embeddings_limit({"chunker": "page"}, E5) == 512


def test_a_model_not_served_is_named() -> None:
    assert chosen_models(["e5"], [MINILM, E5]) == [E5]
    with pytest.raises(InvalidRequest, match=r"\['x'\] aren't served"):
        chosen_models(["x"], [E5])
