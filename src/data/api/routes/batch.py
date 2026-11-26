"""POST /batch (feature 022): many nodes and relationships in one request and one transaction (all or nothing).

Everything is validated before writing: labels and types by the enums (FastAPI), the rest by
data.schema.batch_problems (relationships by the schema, no node or relationship repeated). If something fails, 422
and nothing is written.
"""

from fastapi import APIRouter, HTTPException, status

from data.api.dependencies import Repository
from data.api.schemas import NEO4J_DOWN, Batch, error
from data.models import BatchError, BatchResult, Relationship
from data.schema import batch_problems

router = APIRouter(tags=["batch"])


@router.post(
    "/batch",
    responses={
        422: error("the batch doesn't follow the schema or a relationship end is missing"),
        503: error(NEO4J_DOWN),
    },
)
def write_batch(repository: Repository, batch: Batch) -> BatchResult:
    """Deletes the descendants of `replace_from` (through ES, TIENE_SECCION, TIENE_FRAGMENTO, TIENE, GENERA,
    EXP_TIENE_DOCUMENTO, EXP_TIENE_SECCION, EXP_TIENE_CHUNK, EXP_TIENE_VECTOR, EXP_GENERA_VECTOR, PIPE_TIENE_ITERACION
    and PIPE_TIENE_EVENTO; never the node itself nor what is above it), then merges every node by id (`mode:
    "replace"` replaces its properties, `"ensure"` only creates it if missing and never touches an existing one,
    `"merge"` sets the ones sent and keeps the others) and every relationship (its properties are replaced)."""
    relationships = [Relationship(r.type, r.source, r.target, r.properties) for r in batch.relationships]
    problems = batch_problems(batch.nodes, relationships)
    if problems:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "; ".join(problems))
    try:
        return repository.write_batch(batch.nodes, relationships, batch.replace_from)
    except BatchError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from e
