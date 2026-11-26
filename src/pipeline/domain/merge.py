"""Configurations over configurations: a stage's params, the run's, and each cycle iteration's `next`."""

from pipeline.models import JsonObject


def deep_merge(base: JsonObject, over: JsonObject) -> JsonObject:
    """`base` with `over` on top: objects are merged key by key, anything else is replaced; a null removes the key."""
    merged = dict(base)
    for key, value in over.items():
        current = merged.get(key)
        if value is None:
            merged.pop(key, None)
        elif isinstance(value, dict) and isinstance(current, dict):
            merged[key] = deep_merge(current, value)
        else:
            merged[key] = value
    return merged
