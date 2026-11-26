"""selection_from_json (feature 062): the rules of `files`, each a 422 that says which; and a sample."""

import pytest

from pipeline.domain.batches import sampled
from pipeline.domain.codec import selection_from_json, selection_to_json
from pipeline.models import InvalidRequest, JsonObject, Selection


@pytest.mark.parametrize(
    ("files", "message"),
    [
        ({}, "exactly one of"),
        ({"all": True, "sample": 3}, "exactly one of"),
        ({"pages": {"from": 1, "to": 2}}, "`pages` needs `per_page`"),
        ({"all": True, "per_page": 5}, "`per_page` only goes with `pages`"),
        ({"all": True, "seed": 7}, "`seed` only goes with `sample`"),
        ({"sha256s": ["a"], "types": ["pdf"]}, "not with `sha256s`"),
        ({"all": True, "month": 3}, "`month` only goes with `year`"),
        ({"all": True, "year": 2024, "week": "Semana_01"}, "`week` only goes with `month`"),
        ({"sample": 0}, "sample must be at least 1"),
    ],
)
def test_a_selection_that_breaks_a_rule_says_which(files: JsonObject, message: str) -> None:
    with pytest.raises(InvalidRequest, match=message):
        selection_from_json(files)


def test_a_sample_with_filters_and_seed_goes_and_comes_back() -> None:
    files: JsonObject = {"sample": 300, "seed": 7, "types": ["pdf"], "year": 2024}
    selection = selection_from_json(files)
    assert selection == Selection(sample=300, seed=7, types=("pdf",), year=2024)
    assert selection_to_json(selection) == files


def test_a_seeded_sample_repeats_and_is_in_sha256_order() -> None:
    ids = [f"s{i:02}" for i in range(30)]
    first = sampled(ids, 5, 7)
    assert first == sampled(list(reversed(ids)), 5, 7) and first == sorted(first) and len(first) == 5
    assert sampled(ids, 5, 8) != first


def test_a_sample_larger_than_the_ids_takes_them_all() -> None:
    assert sampled(["b", "a"], 5, None) == ["a", "b"] and len(sampled([f"{i}" for i in range(9)], 3, None)) == 3
