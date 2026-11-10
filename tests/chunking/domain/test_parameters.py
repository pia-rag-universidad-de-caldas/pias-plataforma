"""Parameters (feature 043): the configurable part resolved, checked and, for POST /runs, the active one."""

import pytest

from chunking.config import CHUNKING_VERSION
from chunking.domain import InvalidParameters, Parameters
from chunking.models import ActiveConfig, ConfigOrigin, DoclingChunker, NoConfiguration, RequestedChunking

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
