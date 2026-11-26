"""A template's stages as a flow diagram (feature 039), and the changes it allows: what is drawn and edited is the list
of stages as the API gives it, and the API has the last word on whether they can run in that order."""

from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass

from .bodies import JsonObject, JsonValue
from .cards import fit

CYCLE = "cycle"
MIN_WIDTH = 40
MAX_WIDTH = 72
BOX_HEIGHT = 3

type Stages = list[JsonObject]


@dataclass(frozen=True)
class Box:
    """Where a stage is drawn; a cycle's box is the first line of its frame."""

    id: str
    x: int
    y: int
    width: int
    height: int
    cycle: bool = False


@dataclass(frozen=True)
class Diagram:
    lines: tuple[str, ...]
    boxes: tuple[Box, ...]  # in the order of the flow

    def box(self, id: str) -> Box | None:
        return next((box for box in self.boxes if box.id == id), None)

    def at(self, x: int, y: int) -> str | None:
        """The stage under a click."""
        for box in self.boxes:
            if box.x <= x < box.x + box.width and box.y <= y < box.y + box.height:
                return box.id
        return None


def _children(stage: JsonObject) -> Stages:
    found = stage.get("stages")
    return [s for s in found if isinstance(s, dict)] if isinstance(found, list) else []


def _is_cycle(stage: JsonObject) -> bool:
    return stage.get("action") == CYCLE


def _text(stage: JsonObject) -> str:
    who = f" · espera a {stage['actor']}" if stage.get("actor") else ""
    return f"{stage.get('id')} · {stage.get('action')}{who}"


def _stage_lines(stage: JsonObject, width: int) -> list[str]:
    inner = width - 4
    return ["╭" + "─" * (width - 2) + "╮", f"│ {fit(_text(stage), inner):<{inner}} │", "╰" + "─" * (width - 2) + "╯"]


def _arrow(width: int) -> str:
    return " " * (width // 2) + "▼"


def _cycle_title(stage: JsonObject, width: int) -> str:
    limit = stage.get("max_iterations")
    parts = [f"↻ {stage.get('id')}", f"aprueba {stage.get('actor') or '?'}"]
    if limit is not None:
        parts.append(f"máx. {limit}")
    title = fit(" · ".join(str(p) for p in parts), width - 5)
    return f"╭─ {title} " + "─" * max(width - len(title) - 5, 0) + "╮"


def layout(stages: Sequence[JsonObject], available: int) -> Diagram:
    """Top to bottom, from inicio to fin. A cycle is a frame with its stages inside and the way back on its left."""
    width = max(MIN_WIDTH, min(available, MAX_WIDTH))
    lines: list[str] = [" " * (width // 2 - 3) + "( inicio )", _arrow(width)]
    boxes: list[Box] = []
    for stage in stages:
        if _is_cycle(stage):
            boxes.append(Box(str(stage.get("id")), 0, len(lines), width, 1, cycle=True))
            lines.append(_cycle_title(stage, width))
            inner = width - 8
            steps = _children(stage)
            for position, step in enumerate(steps):
                boxes.append(Box(str(step.get("id")), 6, len(lines), inner, BOX_HEIGHT))
                back = "┌▶" if position == 0 else "│ "
                for row, text in enumerate(_stage_lines(step, inner)):
                    mark = back if row == 1 else ("│ " if position or row else "  ")
                    lines.append(f"│ {mark}  {text} │")
                if position < len(steps) - 1:
                    lines.append(f"│ │   {' ' * (inner // 2)}▼".ljust(width - 1) + "│")
            note = "si no se aprueba, otra iteración"
            lines.append(f"│ └── {note}".ljust(width - 1) + "│")
            lines.append("╰" + "─" * (width - 2) + "╯")
        else:
            boxes.append(Box(str(stage.get("id")), 0, len(lines), width, BOX_HEIGHT))
            lines.extend(_stage_lines(stage, width))
        lines.append(_arrow(width))
    lines.append(" " * (width // 2 - 2) + "( fin )")
    return Diagram(tuple(lines), tuple(boxes))


def describe(stages: Sequence[JsonObject], id: str) -> str:
    """Everything a stage has, for the line under the diagram."""
    found = find(stages, id)
    if found is None:
        return ""
    parts = [f"{id}: {found.get('action')}"]
    for key, name in (("actor", "actor"), ("max_iterations", "máx."), ("needs", "necesita"), ("gives", "da")):
        if found.get(key):
            parts.append(f"{name} {found[key]}")
    if found.get("params"):
        parts.append(f"parámetros {found['params']}")
    return " · ".join(parts)


# --- changes: each one returns new stages and leaves the given ones as they were ---


def ids(stages: Sequence[JsonObject]) -> list[str]:
    """In the order of the flow."""
    return [i for s in stages for i in (str(s.get("id")), *ids(_children(s)))]


def find(stages: Sequence[JsonObject], id: str) -> JsonObject | None:
    for stage in stages:
        if stage.get("id") == id:
            return stage
        found = find(_children(stage), id)
        if found is not None:
            return found
    return None


def _owner(stages: Stages, id: str) -> tuple[Stages, int, JsonObject | None] | None:
    """The list that has it, its place and, if that list is a cycle's, the cycle."""
    for index, stage in enumerate(stages):
        if stage.get("id") == id:
            return stages, index, None
    for stage in stages:
        inner = _children(stage)
        for index, step in enumerate(inner):
            if step.get("id") == id:
                return inner, index, stage
    return None


def _set_children(cycle: JsonObject, steps: Stages) -> None:
    listed: list[JsonValue] = list(steps)
    cycle["stages"] = listed


def move(stages: Sequence[JsonObject], id: str, down: bool) -> Stages:
    """One place along the flow: past a neighbour, into a cycle it reaches or out of the one it is in. A cycle goes past
    the stage or cycle next to it: a cycle can't be inside another one."""
    copied = deepcopy(list(stages))
    found = _owner(copied, id)
    if found is None:
        return copied
    owner, index, cycle = found
    stage = owner[index]
    target = index + (1 if down else -1)
    if cycle is None:
        if not 0 <= target < len(copied):
            return copied
        neighbour = copied[target]
        if _is_cycle(neighbour) and not _is_cycle(stage):
            steps = _children(neighbour)
            del copied[index]
            _set_children(neighbour, [stage, *steps] if down else [*steps, stage])
            return copied
        copied[index], copied[target] = neighbour, stage
        return copied
    if 0 <= target < len(owner):
        steps = list(owner)
        steps[index], steps[target] = steps[target], stage
        _set_children(cycle, steps)
        return copied
    _set_children(cycle, [s for s in owner if s is not stage])
    place = next(i for i, s in enumerate(copied) if s is cycle)
    copied.insert(place + 1 if down else place, stage)
    return copied


def remove(stages: Sequence[JsonObject], id: str) -> Stages:
    copied = deepcopy(list(stages))
    found = _owner(copied, id)
    if found is None:
        return copied
    owner, index, cycle = found
    if cycle is None:
        del copied[index]
    else:
        _set_children(cycle, [s for i, s in enumerate(owner) if i != index])
    return copied


def insert_after(stages: Sequence[JsonObject], id: str | None, new: JsonObject) -> Stages:
    """Right after `id`, in its same list; at the end without it. A cycle can't go inside a cycle: it goes after it."""
    copied = deepcopy(list(stages))
    found = _owner(copied, id) if id is not None else None
    if found is None:
        copied.append(new)
        return copied
    owner, index, cycle = found
    if cycle is None:
        copied.insert(index + 1, new)
    elif _is_cycle(new):
        place = next(i for i, s in enumerate(copied) if s is cycle)
        copied.insert(place + 1, new)
    else:
        _set_children(cycle, [*owner[: index + 1], new, *owner[index + 1 :]])
    return copied


def replace_stage(stages: Sequence[JsonObject], id: str, new: JsonObject) -> Stages:
    copied = deepcopy(list(stages))
    found = _owner(copied, id)
    if found is None:
        return copied
    owner, index, cycle = found
    if cycle is None:
        copied[index] = new
    else:
        _set_children(cycle, [new if i == index else s for i, s in enumerate(owner)])
    return copied


def mini(stages: Sequence[JsonObject]) -> str:
    """The flow in one line, for a template's card."""
    return " → ".join(f"↻{s.get('id')}" if _is_cycle(s) else str(s.get("id")) for s in stages)
