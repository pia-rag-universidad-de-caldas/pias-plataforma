"""pair (feature 044): a laboratory iteration's chunking and embeddings configurations made to fit the model; fit_llm
(feature 050): its llm, admitted and downloaded."""

import pytest

from pipeline.config import SPECIAL_TOKENS
from pipeline.domain import LABORATORY, PRODUCTION, check_cycles, fit_llm, lab_cycles, pair
from pipeline.models import EmbeddingModel, InvalidRequest, JsonObject, LlmModel

MINILM = EmbeddingModel("paraphrase-multilingual-MiniLM-L12-v2", default_tokens=128, max_tokens=512, default=True)
OTHER = EmbeddingModel("otro", default_tokens=256, max_tokens=256)
QWEN = LlmModel("qwen", context=8192, installed=True, default=True)
BIG = LlmModel("grande", context=32768)  # admitted, not downloaded


def test_without_max_tokens_it_is_the_model_default_minus_the_special_tokens() -> None:
    fitted = pair({"chunking": {"chunker": "hybrid"}}, [MINILM, OTHER])
    assert fitted.chunking == {"chunker": "hybrid", "tokenizer": MINILM.name, "max_tokens": 126}
    assert fitted.embeddings == {"model": MINILM.name, "max_tokens": 128}
    assert SPECIAL_TOKENS == 2


def test_embeddings_gets_chunkings_max_tokens_plus_the_special_tokens() -> None:
    fitted = pair({"chunking": {"max_tokens": 300}, "embeddings": {"model": MINILM.name}}, [MINILM])
    assert fitted.chunking["max_tokens"] == 300 and fitted.embeddings["max_tokens"] == 302


def test_the_largest_max_tokens_is_the_limit_minus_the_special_tokens() -> None:
    assert pair({"chunking": {"max_tokens": 510}}, [MINILM]).embeddings["max_tokens"] == 512
    with pytest.raises(InvalidRequest, match="can't pass 510"):
        pair({"chunking": {"max_tokens": 511}}, [MINILM])


def test_other_chunkers_have_no_max_tokens_and_embeddings_gets_the_models_limit() -> None:
    fitted = pair({"chunking": {"chunker": "page"}, "embeddings": {"model": "otro"}}, [MINILM, OTHER])
    assert "max_tokens" not in fitted.chunking and fitted.embeddings["max_tokens"] == 256


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({"embeddings": {"model": "nope"}}, "isn't admitted"),
        ({"chunking": {"tokenizer": "other"}}, "must be the embeddings model"),
        ({"chunking": {"max_tokens": 0}}, "positive integer"),
        ({"chunking": {"max_tokens": 100}, "embeddings": {"max_tokens": 50}}, "leave it out"),
    ],
)
def test_what_doesnt_fit(config: JsonObject, message: str) -> None:
    with pytest.raises(InvalidRequest, match=message):
        pair(config, [MINILM])


def test_without_a_default_model_it_must_be_said() -> None:
    with pytest.raises(InvalidRequest, match=r"say embeddings\.model"):
        pair({}, [OTHER, EmbeddingModel("tercero", 64, 64)])


def test_only_the_laboratory_has_a_pair_and_it_is_checked_with_the_runs_params() -> None:
    assert [c.id for c in lab_cycles(LABORATORY.stages)] == ["laboratorio"] and lab_cycles(PRODUCTION.stages) == []
    check_cycles(LABORATORY.stages, {}, [MINILM])
    with pytest.raises(InvalidRequest, match="can't pass"):
        check_cycles(LABORATORY.stages, {"laboratorio": {"chunking": {"max_tokens": 600}}}, [MINILM])


def test_an_iteration_without_llm_asks_nothing_of_llm() -> None:
    def never() -> list[LlmModel]:
        raise AssertionError("llm was asked")

    assert fit_llm({"chunking": {}}, []) is None
    check_cycles(LABORATORY.stages, {}, [MINILM], never)


def test_an_admitted_and_downloaded_llm_fits() -> None:
    llm: JsonObject = {"model": "qwen", "temperature": 0.2, "num_ctx": 4096, "max_tokens": 300, "system": "breve"}
    assert fit_llm({"llm": llm}, [QWEN, BIG]) == llm


@pytest.mark.parametrize(
    ("llm", "message"),
    [
        ({}, r"say llm\.model"),
        ({"model": "nope"}, "isn't admitted"),
        ({"model": "grande"}, "isn't downloaded"),
        ({"model": "qwen", "top_p": 1}, "doesn't take"),
        ({"model": "qwen", "temperature": -1}, "at least 0"),
        ({"model": "qwen", "num_ctx": 0}, "positive integer"),
        ({"model": "qwen", "num_ctx": 9000}, "context of qwen"),
        ({"model": "qwen", "system": 3}, "a text"),
    ],
)
def test_an_llm_that_cant_be_used(llm: JsonObject, message: str) -> None:
    with pytest.raises(InvalidRequest, match=message):
        fit_llm({"llm": llm}, [QWEN, BIG])


def test_the_runs_llm_is_checked_before_it_starts() -> None:
    with pytest.raises(InvalidRequest, match="isn't downloaded"):
        check_cycles(LABORATORY.stages, {"laboratorio": {"llm": {"model": "grande"}}}, [MINILM], lambda: [QWEN, BIG])
