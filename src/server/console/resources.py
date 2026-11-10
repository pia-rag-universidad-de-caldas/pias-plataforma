"""A module's operations grouped by resource (the first part of their path), in the order the module declares them."""

from collections.abc import Sequence
from dataclasses import dataclass

from . import texts
from .catalog import Operation


@dataclass(frozen=True)
class Action:
    operation: Operation
    name: str
    effect: str


@dataclass(frozen=True)
class Resource:
    segment: str
    name: str
    description: str
    actions: tuple[Action, ...]


def action(operation: Operation) -> Action:
    found = texts.action(
        operation.module.name, operation.method, operation.path, operation.summary, operation.description
    )
    return Action(operation, found.name, found.description)


def group(operations: tuple[Operation, ...]) -> tuple[Resource, ...]:
    """Every operation in exactly one resource."""
    segments: dict[str, list[Action]] = {}
    for operation in operations:
        segments.setdefault(operation.segment, []).append(action(operation))
    found: list[Resource] = []
    for segment, actions in segments.items():
        text = texts.resource(actions[0].operation.module.name, segment)
        found.append(Resource(segment, text.name, text.description, tuple(actions)))
    return tuple(found)


HEALTH = "health"  # always on screen: it has no card (feature 039)
PROCESSES = "processes"
SCHEMA = "schema"
PROGRESS = "progress"  # data: its own screen, parsing and chunking at a glance (features 042 and 043)
TEMPLATES = "pipelines"
EXPERIMENTS = "experiments"


def main_resources(resources: Sequence[Resource]) -> list[Resource]:
    """What a module's menu shows: the experiments first, and no card for its health."""
    shown = [r for r in resources if r.segment != HEALTH]
    return sorted(shown, key=lambda r: r.segment != EXPERIMENTS)
