"""A module's operations grouped by resource (the first part of their path), in the order the module declares them."""

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
