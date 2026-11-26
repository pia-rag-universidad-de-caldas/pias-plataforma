"""Check (feature 042): what has to be parsed, and the fingerprint that decides it."""

from dataclasses import replace

import pytest

from parsing.config import PARSING
from parsing.domain import Check, fingerprint
from parsing.models import ParseStatus, RawState

DONE = RawState("a", True, ParseStatus.PARSED, "f1")


@pytest.mark.parametrize(
    ("state", "pending"),
    [
        (DONE, False),
        (replace(DONE, status=ParseStatus.PARTIAL), True),
        (replace(DONE, status=ParseStatus.ERROR), True),
        (replace(DONE, fingerprint="other"), True),
        (RawState("a"), True),
    ],
    ids=["parsed", "partial", "error", "other fingerprint", "never parsed"],
)
def test_only_a_whole_parsing_with_this_fingerprint_is_done(state: RawState, pending: bool) -> None:
    assert Check.done(state, "f1") is not pending


def test_pending_are_the_current_raw_not_done() -> None:
    states = [RawState("c"), DONE, RawState("b", vigente=False)]
    assert [s.sha256 for s in Check.pending(states, "f1")] == ["c"]


def test_with_redo_every_current_raw_is_pending() -> None:
    states = [RawState("c"), DONE, RawState("b", vigente=False)]
    assert [s.sha256 for s in Check.pending(states, "f1", redo=True)] == ["a", "c"]


def test_the_fingerprint_changes_with_docling_and_with_the_version() -> None:
    base = fingerprint(PARSING, 1, "2.148.0")
    assert base == fingerprint(PARSING, 1, "2.148.0")
    assert base != fingerprint(PARSING, 2, "2.148.0")
    assert base != fingerprint(PARSING, 1, "2.149.0")
    assert base != fingerprint(replace(PARSING, ocr=False), 1, "2.148.0")
