"""deep_merge: the configuration of each cycle iteration is the previous one with `next` on top."""

from pipeline.domain import deep_merge
from pipeline.models import JsonObject


def test_objects_merge_by_key_other_values_replace_and_null_removes() -> None:
    base: JsonObject = {
        "conversion": {"heading_level": 1, "table_mode": "accurate"},
        "plan": {"rules": [1]},
        "keep": True,
    }
    over: JsonObject = {"conversion": {"heading_level": 2, "table_mode": None}, "plan": {"rules": [2]}, "new": "x"}
    assert deep_merge(base, over) == {
        "conversion": {"heading_level": 2},
        "plan": {"rules": [2]},  # lists are replaced, not appended
        "keep": True,
        "new": "x",
    }


def test_the_base_is_not_changed() -> None:
    base: JsonObject = {"a": {"b": 1}}
    deep_merge(base, {"a": {"b": 2}})
    assert base == {"a": {"b": 1}}
