"""Chunking rules without I/O: what is pending (Selection), the parameters of each strategy (Parameters) and which
rule of a plan takes each section (Planner)."""

import pytest

from chunking.domain import InvalidParameters, Parameters, Planner, Selection
from chunking.models import (
    ChunkingStrategy,
    ConvertedDocument,
    DocumentSection,
    DocumentStatus,
    Match,
    Plan,
    PositionRange,
    ProcessedDocument,
    RequestedStrategy,
    Rule,
    SourceDocument,
)

DOC = SourceDocument("2024/a.pdf", "v/a.pdf", "a.pdf", "h1", "pdf", 2024, "020055")


def done(
    sha256: str = "h1", fingerprint: str = "f1", status: DocumentStatus = DocumentStatus.CHUNKED
) -> ProcessedDocument:
    return ProcessedDocument(DOC.origin, sha256, fingerprint, status)


@pytest.mark.parametrize(
    ("processed", "retry", "pending"),
    [
        (None, False, True),  # new
        (done(), False, False),  # same content and parameters
        (done(sha256="h0"), False, True),  # the origin has another content now
        (done(fingerprint="f0"), False, True),  # chunked with other parameters
        (done(status=DocumentStatus.ERROR), False, False),  # failed with these parameters: only with retry_errors
        (done(status=DocumentStatus.ERROR), True, True),
        (done(fingerprint="f0", status=DocumentStatus.ERROR), False, True),  # other parameters may fix it
    ],
)
def test_pending(processed: ProcessedDocument | None, retry: bool, pending: bool) -> None:
    assert Selection.is_pending(DOC, processed, "f1", retry) is pending


def test_pending_keeps_the_page_order() -> None:
    other = SourceDocument("2024/b.pdf", "v/b.pdf", "b.pdf", "h2", "pdf", 2024, None)
    assert Selection.pending([other, DOC], {DOC.origin: done()}, "f1", False) == [other]


def test_parameters_take_defaults_and_only_what_the_strategy_uses() -> None:
    hybrid = Parameters.resolve(RequestedStrategy())
    assert hybrid.strategy is ChunkingStrategy.HYBRID and hybrid.max_tokens == 512 and hybrid.overlap_tokens is None
    element = Parameters.resolve(RequestedStrategy(strategy=ChunkingStrategy.ELEMENT))
    assert element.max_tokens is None and element.merge_peers is None
    fixed = Parameters.resolve(RequestedStrategy(strategy=ChunkingStrategy.FIXED, max_tokens=100, overlap_tokens=20))
    assert (fixed.max_tokens, fixed.overlap_tokens) == (100, 20)


@pytest.mark.parametrize(
    ("asked", "message"),
    [
        (RequestedStrategy(strategy=ChunkingStrategy.ELEMENT, max_tokens=100), "doesn't use max_tokens"),
        (RequestedStrategy(overlap_tokens=10), "doesn't use overlap_tokens"),
        (RequestedStrategy(tokenizer="gpt2"), "isn't allowed"),
        (RequestedStrategy(max_tokens=8), "max_tokens must be between"),
        (
            RequestedStrategy(strategy=ChunkingStrategy.FIXED, max_tokens=100, overlap_tokens=100),
            "less than max_tokens",
        ),
        (RequestedStrategy(strategy=ChunkingStrategy.SEMANTIC, embedding_model="x"), "isn't allowed"),
        (RequestedStrategy(strategy=ChunkingStrategy.SEMANTIC, similarity_threshold=1.5), "between 0 and 1"),
    ],
)
def test_parameters_never_ignore_a_wrong_value(asked: RequestedStrategy, message: str) -> None:
    with pytest.raises(InvalidParameters, match=message):
        Parameters.resolve(asked)


def section(title: str) -> DocumentSection:
    return DocumentSection(title, 1, [1], [])


def test_the_first_matching_rule_wins_and_the_rest_take_the_default() -> None:
    points = Parameters.resolve(RequestedStrategy(strategy=ChunkingStrategy.POINTS))
    page = Parameters.resolve(RequestedStrategy(strategy=ChunkingStrategy.PAGE))
    default = Parameters.resolve(RequestedStrategy())
    plan = Plan(
        [
            Rule(Match(titles=["objetivo"]), points),
            Rule(Match(titles=["OBJETIVOS ESPECÍFICOS"]), page),  # never reached: rule 0 takes it first
            Rule(Match(position=PositionRange(0.75, 1.0)), page),
        ],
        default,
    )
    document = ConvertedDocument(
        "", [section("Justificación"), section("  Objetivos  específicos"), section("X"), section("Bibliografía")]
    )
    assigned = [(a.rule, a.parameters.strategy) for a in Planner.assign(document, plan)]
    assert assigned == [
        (None, ChunkingStrategy.HYBRID),
        (0, ChunkingStrategy.POINTS),  # without accents nor case, single spaces
        (None, ChunkingStrategy.HYBRID),  # its middle (0.625) is before 0.75
        (2, ChunkingStrategy.PAGE),
    ]


@pytest.mark.parametrize(
    "match",
    [Match(), Match(titles=["  "]), Match(position=PositionRange(0.5, 0.2)), Match(position=PositionRange(0, 2))],
)
def test_a_rule_that_takes_nothing_is_invalid(match: Match) -> None:
    with pytest.raises(InvalidParameters):
        Planner.check(match)
