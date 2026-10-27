"""POST /batch (feature 022): many nodes and relationships in one request and one transaction (all or nothing).

Everything is validated before writing: labels and types by the enums (FastAPI), relationships by the schema, no
node or relationship repeated. If something fails, 422 and nothing is written.
"""

from collections import Counter

from fastapi import APIRouter, HTTPException, status

from data.api.dependencies import Repository
from data.api.schemas import NEO4J_DOWN, Batch, error
from data.models import BatchError, BatchResult, Relationship
from data.schema import definition

router = APIRouter(tags=["batch"])


def _problems(batch: Batch) -> list[str]:
    """Everything wrong with the batch before touching the graph; empty if it can be written."""
    problems = [f"empty id in a {n.label} node" for n in batch.nodes if not n.id]
    nodes = Counter((n.label, n.id) for n in batch.nodes)
    problems += [f"the {label} node {id!r} comes {times} times" for (label, id), times in nodes.items() if times > 1]
    for r in batch.relationships:
        if definition(r.type, r.source.label, r.target.label) is None:
            problems.append(f"the schema doesn't allow ({r.source.label})-[:{r.type}]->({r.target.label})")
    keys = Counter((r.type, r.source, r.target) for r in batch.relationships)
    problems += [
        f"({s.label} {s.id!r})-[:{t}]->({e.label} {e.id!r}) comes {times} times"
        for (t, s, e), times in keys.items()
        if times > 1
    ]
    return problems


@router.post(
    "/batch",
    responses={
        422: error("the batch doesn't follow the schema or a relationship end is missing"),
        503: error(NEO4J_DOWN),
    },
)
def write_batch(repository: Repository, batch: Batch) -> BatchResult:
    """Deletes the descendants of `replace_from` (through ES, TIENE_SECCION, TIENE_FRAGMENTO, TIENE, GENERA, EXP_GENERA,
    EXP_TIENE_CHUNK, EXP_TIENE_PUNTUACION, PIPE_TIENE_ITERACION and PIPE_TIENE_EVENTO; never the node itself nor what
    is above it), then merges every node by id (`mode: "replace"` replaces its properties, `"ensure"` only creates it
    if missing and never touches an existing one, `"merge"` sets the ones sent and keeps the others) and every
    relationship (its properties are replaced)."""
    problems = _problems(batch)
    if problems:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "; ".join(problems))
    relationships = [Relationship(r.type, r.source, r.target, r.properties) for r in batch.relationships]
    try:
        return repository.write_batch(batch.nodes, relationships, batch.replace_from)
    except BatchError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
