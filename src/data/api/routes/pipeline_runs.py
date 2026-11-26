"""Read only the waiting pipeline runs for the review inbox, without scanning completed history."""

from typing import Annotated

from fastapi import APIRouter, Query

from data.api.dependencies import Paginated, Repository
from data.api.schemas import NEO4J_DOWN, NodePage, error

router = APIRouter(prefix="/pipeline/runs", tags=["pipeline"])


@router.get("", responses={503: error(NEO4J_DOWN)})
def runs_by_status(
    repository: Repository,
    pagination: Paginated,
    status: Annotated[str, Query(min_length=1)],
    actor: Annotated[str | None, Query(min_length=1)] = None,
) -> NodePage:
    """One page of pipeline runs for a status, optionally filtered to one waiting actor."""
    total = repository.count_pipeline_runs(status, actor)
    return NodePage(
        page=pagination.page,
        per_page=pagination.per_page,
        total=total,
        pages=pagination.pages(total),
        nodes=repository.pipeline_runs(status, actor, pagination.skip, pagination.per_page),
    )


__all__ = ["router"]
