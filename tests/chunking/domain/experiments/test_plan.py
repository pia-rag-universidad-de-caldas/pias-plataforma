"""Planner (feature 025): which rule of a plan takes each section."""

import pytest

from chunking.domain import InvalidParameters, Parameters, Planner
from chunking.models import (
    ChunkingStrategy,
    ConvertedDocument,
    DocumentSection,
    Match,
    Plan,
    PositionRange,
    RequestedStrategy,
    Rule,
)


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
