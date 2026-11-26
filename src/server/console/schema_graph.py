"""The graph's schema drawn (feature 039): what each label points to, from the labels nothing points to. A label reached
again isn't drawn twice, it is only named."""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Edge:
    type: str
    source: str
    target: str


@dataclass(frozen=True)
class Line:
    """One line of the drawing, in parts so that each can have its colour."""

    tree: str  # the branches
    relation: str  # the relationship that arrives; "" in a root
    label: str
    repeated: bool = False


def _reach(start: str, edges: Sequence[Edge]) -> int:
    seen = {start}
    pending = [start]
    while pending:
        current = pending.pop()
        for edge in edges:
            if edge.source == current and edge.target not in seen:
                seen.add(edge.target)
                pending.append(edge.target)
    return len(seen)


def roots(labels: Sequence[str], edges: Sequence[Edge]) -> list[str]:
    """Those nothing points to, those that reach more first; `labels` gives the order among equals."""
    pointed = {edge.target for edge in edges}
    used = {edge.source for edge in edges}
    found = [label for label in labels if label in used and label not in pointed]
    return sorted(found, key=lambda label: -_reach(label, edges))


def draw(labels: Sequence[str], edges: Sequence[Edge]) -> list[Line]:
    """Every label and every relationship, once: a cycle with no root is started from its first label not drawn yet."""
    drawn: set[str] = set()
    lines: list[Line] = []

    def branch(label: str, tree: str) -> None:
        children = [edge for edge in edges if edge.source == label]
        for index, edge in enumerate(children):
            last = index == len(children) - 1
            again = edge.target in drawn
            lines.append(Line(f"{tree}{'└─' if last else '├─'} ", edge.type, edge.target, again))
            if not again:
                drawn.add(edge.target)
                branch(edge.target, f"{tree}{'   ' if last else '│  '}")

    def tree_from(root: str) -> None:
        if lines:
            lines.append(Line("", "", ""))
        drawn.add(root)
        lines.append(Line("", "", root))
        branch(root, "")

    for root in roots(labels, edges):
        tree_from(root)
    for label in labels:
        if label not in drawn and any(edge.source == label for edge in edges):
            tree_from(label)
    for label in labels:
        if label not in drawn:
            tree_from(label)
    return lines
