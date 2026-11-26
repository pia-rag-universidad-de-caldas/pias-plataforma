"""The order of a template's stages: what each one needs must be given by one before it."""

from collections.abc import Sequence
from dataclasses import replace

from pipeline.models import InvalidTemplate, Stage, StageKind, approved

from .actions import REVIEW_SCORE, action


def _step(stage: Stage, available: set[str], in_cycle: bool) -> set[str]:
    """What `stage` gives; InvalidTemplate if it needs something not `available` or can't be where it is."""
    if stage.is_cycle:
        raise InvalidTemplate(f"stage {stage.id!r}: a cycle can't be inside another cycle")
    found = action(stage)
    if found.name == REVIEW_SCORE and not in_cycle:
        raise InvalidTemplate(f"stage {stage.id!r}: {REVIEW_SCORE} only goes inside a cycle")
    if found.kind == StageKind.WAIT and found.name != REVIEW_SCORE and not stage.actor:
        raise InvalidTemplate(f"stage {stage.id!r}: {found.name} needs an `actor`")
    missing = [n for n in found.needs_of(stage) if n not in available]
    if missing:
        raise InvalidTemplate(f"stage {stage.id!r} needs {missing} and no stage before it gives it")
    return set(found.gives_of(stage))


def _cycle(cycle: Stage, available: set[str]) -> set[str]:
    """What the cycle gives once approved: the approved version of what its stages give."""
    if not cycle.actor:
        raise InvalidTemplate(f"cycle {cycle.id!r} needs the `actor` who approves it")
    if not cycle.stages:
        raise InvalidTemplate(f"cycle {cycle.id!r} has no stages")
    if cycle.max_iterations is not None and cycle.max_iterations < 1:
        raise InvalidTemplate(f"cycle {cycle.id!r}: max_iterations must be at least 1")
    if cycle.stages[-1].action != REVIEW_SCORE or any(s.action == REVIEW_SCORE for s in cycle.stages[:-1]):
        raise InvalidTemplate(f"cycle {cycle.id!r}: its last stage, and only that one, must be {REVIEW_SCORE}")
    inner = set(available)
    given: set[str] = set()
    for step in cycle.stages:
        gives = _step(step, inner, in_cycle=True)
        inner |= gives
        given |= gives
    return {approved(g) for g in given}


def _ids(stages: Sequence[Stage]) -> list[str]:
    return [i for s in stages for i in (s.id, *_ids(s.stages))]


def check(stages: Sequence[Stage]) -> None:
    """InvalidTemplate with the stage and what is wrong if the stages can't run in this order."""
    if not stages:
        raise InvalidTemplate("a template needs at least one stage")
    ids = _ids(stages)
    repeated = sorted({i for i in ids if ids.count(i) > 1})
    if repeated:
        raise InvalidTemplate(f"repeated stage ids: {repeated}")
    available: set[str] = set()
    for stage in stages:
        available |= _cycle(stage, available) if stage.is_cycle else _step(stage, available, in_cycle=False)


def reorder(stages: Sequence[Stage], order: Sequence[str]) -> tuple[Stage, ...]:
    """The top-level stages in `order` (exactly their ids, each once). The caller checks the result."""
    by_id = {s.id: s for s in stages}
    if sorted(order) != sorted(by_id):
        raise InvalidTemplate(f"`order` must have each top-level stage id once: {sorted(by_id)}")
    return tuple(by_id[i] for i in order)


def _moved(stages: tuple[Stage, ...], id: str, before: str | None, after: str | None) -> tuple[Stage, ...]:
    reference = before or after or ""
    ids = [s.id for s in stages]
    if reference not in ids:
        raise InvalidTemplate(f"{reference!r} isn't next to {id!r}: a stage moves within its list (or use PUT)")
    if reference == id:
        raise InvalidTemplate("a stage can't move next to itself")
    stage = stages[ids.index(id)]
    rest = [s for s in stages if s.id != id]
    at = [s.id for s in rest].index(reference) + (1 if after else 0)
    return (*rest[:at], stage, *rest[at:])


def move(stages: Sequence[Stage], id: str, before: str | None = None, after: str | None = None) -> tuple[Stage, ...]:
    """`id` moved right before or right after another stage of its own list (the template's or its cycle's)."""
    if (before is None) == (after is None):
        raise InvalidTemplate("exactly one of `before` and `after`")
    top = tuple(stages)
    if any(s.id == id for s in top):
        return _moved(top, id, before, after)
    for i, cycle in enumerate(top):
        if any(s.id == id for s in cycle.stages):
            changed = replace(cycle, stages=_moved(cycle.stages, id, before, after))
            return (*top[:i], changed, *top[i + 1 :])
    raise InvalidTemplate(f"there is no stage {id!r}")
