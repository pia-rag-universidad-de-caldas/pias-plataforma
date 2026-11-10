"""A production run's `scope` (feature 044): it goes to every stage that reads it, as one of its params."""

from collections.abc import Sequence

from pipeline.config import SCOPES
from pipeline.models import InvalidRequest, JsonObject, Stage

from .merge import deep_merge

READS_SCOPE = frozenset({"chunking.promote"})  # the stages whose batch depends on the scope


def scoped(stages: Sequence[Stage], params: dict[str, JsonObject], scope: str | None) -> dict[str, JsonObject]:
    """`params` with {"scope": scope} on each stage that reads it; InvalidRequest if no stage does or it is unknown."""
    if scope is None:
        return params
    if scope not in SCOPES:
        raise InvalidRequest(f"scope must be one of {list(SCOPES)}, not {scope!r}")
    readers = [s.id for s in stages if s.action in READS_SCOPE]
    if not readers:
        raise InvalidRequest("`scope` only goes with a template that chunks into the official graph (produccion)")
    changed = dict(params)
    for id in readers:
        changed[id] = deep_merge(changed.get(id, {}), {"scope": scope})
    return changed
