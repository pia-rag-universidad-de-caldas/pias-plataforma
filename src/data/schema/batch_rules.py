"""What a batch must follow before anything is written (feature 022): the rules of POST /batch, without the API."""

from collections import Counter
from collections.abc import Sequence

from data.models import BatchNode, Relationship

from .piaa_schema import definition


def batch_problems(nodes: Sequence[BatchNode], relationships: Sequence[Relationship]) -> list[str]:
    """Everything wrong with the batch before touching the graph; empty if it can be written: empty ids, repeated
    nodes or relationships and relationships the schema doesn't allow."""
    problems = [f"empty id in a {n.label} node" for n in nodes if not n.id]
    repeated_nodes = Counter((n.label, n.id) for n in nodes)
    problems += [
        f"the {label} node {id!r} comes {times} times" for (label, id), times in repeated_nodes.items() if times > 1
    ]
    for r in relationships:
        if definition(r.type, r.source.label, r.target.label) is None:
            problems.append(f"the schema doesn't allow ({r.source.label})-[:{r.type}]->({r.target.label})")
    keys = Counter((r.type, r.source, r.target) for r in relationships)
    problems += [
        f"({s.label} {s.id!r})-[:{t}]->({e.label} {e.id!r}) comes {times} times"
        for (t, s, e), times in keys.items()
        if times > 1
    ]
    return problems
