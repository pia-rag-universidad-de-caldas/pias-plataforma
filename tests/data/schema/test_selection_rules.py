"""The rules of a selection of documents (feature 062): which fields go together."""

import pytest

from data.schema.selection_rules import Selection, selection_problem


@pytest.mark.parametrize(
    "selection",
    [
        Selection(all=True),
        Selection(sha256s=("a",)),
        Selection(pages=(1, 2), per_page=10, types=("pdf",)),
        Selection(sample=5, seed=7, year=2024, month=3, week="Semana_01"),
    ],
)
def test_a_selection_that_follows_the_rules_has_no_problem(selection: Selection) -> None:
    assert selection_problem(selection) is None


@pytest.mark.parametrize(
    ("selection", "problem"),
    [
        (Selection(), "exactly one"),
        (Selection(all=True, sample=3), "exactly one"),
        (Selection(all=True, per_page=10), "per_page only goes with pages"),
        (Selection(pages=(1, 1)), "pages needs per_page"),
        (Selection(pages=(3, 2), per_page=5), "1 <= from <= to"),
        (Selection(all=True, seed=1), "seed only goes with sample"),
        (Selection(sha256s=("a",), year=2024), "don't go with sha256s"),
        (Selection(all=True, month=3), "month only goes with year"),
        (Selection(all=True, year=2024, week="Semana_01"), "week only goes with month"),
    ],
)
def test_a_broken_rule_is_named(selection: Selection, problem: str) -> None:
    assert problem in (selection_problem(selection) or "")
