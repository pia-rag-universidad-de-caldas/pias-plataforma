"""deep_merge: the configuration of each cycle iteration is the previous one with `next` on top."""

from pipeline.domain import deep_merge
from pipeline.models import JsonObject


def test_objects_merge_by_key() -> None:
    assert deep_merge({"a": {"b": 1, "c": 2}}, {"a": {"b": 3}}) == {"a": {"b": 3, "c": 2}}


def test_a_list_is_replaced_not_appended() -> None:
    assert deep_merge({"rules": [1]}, {"rules": [2]}) == {"rules": [2]}


def test_a_null_removes_the_key() -> None:
    assert deep_merge({"a": {"b": 1, "c": 2}}, {"a": {"c": None}}) == {"a": {"b": 1}}


def test_what_only_one_side_has_stays() -> None:
    assert deep_merge({"keep": True}, {"new": "x"}) == {"keep": True, "new": "x"}


def test_the_base_is_not_changed() -> None:
    base: JsonObject = {"a": {"b": 1}}
    deep_merge(base, {"a": {"b": 2}})
    assert base == {"a": {"b": 1}}
