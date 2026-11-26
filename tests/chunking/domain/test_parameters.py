"""Parameters (feature 043): the configurable part resolved, checked and, for POST /runs, the active one."""

from dataclasses import replace

import pytest

from chunking.config import CHUNKING_VERSION
from chunking.domain import InvalidParameters, Parameters
from chunking.models import (
    ActiveConfig,
    ConfigOrigin,
    DoclingChunker,
    NoConfiguration,
    RequestedChunking,
    TokenBudget,
    fitted_count,
)

MULTILINGUAL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def test_nothing_asked_is_the_default() -> None:
    resolved = Parameters.resolve(RequestedChunking(), "2.106.0")
    assert (resolved.chunker, resolved.tokenizer, resolved.max_tokens, resolved.merge_peers) == (
        DoclingChunker.HYBRID,
        MULTILINGUAL,
        126,  # the embedding model's 128 minus its two special tokens
        True,
    )
    assert (resolved.chunking_version, resolved.docling_version) == (CHUNKING_VERSION, "2.106.0")


@pytest.mark.parametrize("chunker", [DoclingChunker.HIERARCHICAL, DoclingChunker.PAGE])
def test_a_chunker_without_size_has_no_max_tokens_nor_merge_peers(chunker: DoclingChunker) -> None:
    resolved = Parameters.resolve(RequestedChunking(chunker), "")
    assert (resolved.max_tokens, resolved.merge_peers) == (None, None)


@pytest.mark.parametrize(
    "asked",
    [
        RequestedChunking(DoclingChunker.PAGE, max_tokens=200),
        RequestedChunking(DoclingChunker.HIERARCHICAL, merge_peers=False),
    ],
)
def test_a_parameter_the_chunker_doesnt_use_is_refused(asked: RequestedChunking) -> None:
    with pytest.raises(InvalidParameters, match="doesn't use"):
        Parameters.resolve(asked, "")


@pytest.mark.parametrize(
    ("asked", "problem"),
    [(RequestedChunking(tokenizer="any/model"), "isn't allowed"), (RequestedChunking(max_tokens=8), "between")],
)
def test_a_value_out_of_what_is_allowed_is_refused(asked: RequestedChunking, problem: str) -> None:
    with pytest.raises(InvalidParameters, match=problem):
        Parameters.resolve(asked, "")


def test_the_fingerprint_changes_with_any_parameter() -> None:
    one = Parameters.resolve(RequestedChunking(max_tokens=100), "1")
    assert one.fingerprint != Parameters.resolve(RequestedChunking(max_tokens=101), "1").fingerprint
    assert one.fingerprint != Parameters.resolve(RequestedChunking(max_tokens=100), "2").fingerprint


def test_requested_gives_back_what_resolve_resolved() -> None:
    resolved = Parameters.resolve(RequestedChunking(DoclingChunker.HYBRID, max_tokens=64), "")
    assert Parameters.resolve(Parameters.requested(resolved), "") == resolved


def test_without_a_stored_configuration_the_default_is_active() -> None:
    parameters, used = Parameters.active(None, "")
    assert used.origin is ConfigOrigin.DEFAULT and parameters.max_tokens == 126


def test_a_stored_configuration_is_active() -> None:
    stored = ActiveConfig(RequestedChunking(DoclingChunker.PAGE), ConfigOrigin.MANUAL, None, "2026")
    parameters, used = Parameters.active(stored, "")
    assert used == stored and parameters.chunker is DoclingChunker.PAGE


def test_a_stored_configuration_that_cant_be_used_falls_back_to_the_default() -> None:
    stored = ActiveConfig(RequestedChunking(tokenizer="gone/model"), ConfigOrigin.MANUAL, None, "2026")
    assert Parameters.active(stored, "")[1].origin is ConfigOrigin.DEFAULT


def test_without_any_usable_configuration_there_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("chunking.domain.parameters.TOKENIZERS", ())
    with pytest.raises(NoConfiguration, match="defecto"):
        Parameters.active(None, "")


# Feature 062: fit, several tokenizers at once.

E5 = "intfloat/multilingual-e5-base"
FIT = (TokenBudget(MULTILINGUAL, 126), TokenBudget(E5, 300))


def test_fit_takes_its_first_tokenizer_for_the_tokens_of_a_chunk() -> None:
    resolved = Parameters.resolve(RequestedChunking(fit=FIT), "")
    assert (resolved.tokenizer, resolved.max_tokens, resolved.fit, resolved.merge_peers) == (
        MULTILINGUAL,
        126,
        FIT,
        True,
    )
    assert Parameters.requested(resolved) == RequestedChunking(DoclingChunker.HYBRID, merge_peers=True, fit=FIT)


def test_fit_enters_the_fingerprint_but_an_empty_one_leaves_it_as_before() -> None:
    plain = Parameters.resolve(RequestedChunking(), "")
    assert replace(plain, fit=()).fingerprint == plain.fingerprint
    assert replace(plain, fit=FIT).fingerprint != plain.fingerprint


@pytest.mark.parametrize(
    ("asked", "problem"),
    [
        (RequestedChunking(DoclingChunker.PAGE, fit=FIT), "only goes with the hybrid"),
        (RequestedChunking(tokenizer=MULTILINGUAL, fit=FIT), "not both"),
        (RequestedChunking(max_tokens=64, fit=FIT), "not both"),
        (RequestedChunking(fit=()), "at least one"),
        (RequestedChunking(fit=(FIT[0], FIT[0])), "repeats"),
        (RequestedChunking(fit=(TokenBudget("any/model", 64),)), "isn't allowed"),
        (RequestedChunking(fit=(TokenBudget(E5, 4),)), "between"),
    ],
)
def test_a_fit_that_cant_be_is_invalid(asked: RequestedChunking, problem: str) -> None:
    with pytest.raises(InvalidParameters, match=problem):
        Parameters.resolve(asked, "")


@pytest.mark.parametrize("model", ["intfloat/multilingual-e5-base", "BAAI/bge-m3"])
def test_the_tokenizers_of_the_other_embedding_models_are_allowed(model: str) -> None:
    assert Parameters.resolve(RequestedChunking(tokenizer=model), "").tokenizer == model


@pytest.mark.parametrize("budgets", [[126, 300], [100, 100, 512], [16, 8192]])
def test_the_fitted_count_is_within_the_smallest_budget_exactly_when_each_count_is_within_its_own(
    budgets: list[int],
) -> None:
    smallest = min(budgets)
    for scale in range(0, 3 * max(budgets), 7):
        counts = [scale * b // max(budgets) + i for i, b in enumerate(budgets)]
        fits = all(c <= b for c, b in zip(counts, budgets, strict=True))
        assert (fitted_count(counts, budgets) <= smallest) is fits
