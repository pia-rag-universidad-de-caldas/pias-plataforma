"""GET /actions: the catalog of actions a stage can be."""

from fastapi import APIRouter

from pipeline.api.schemas import ActionView
from pipeline.api.views import action_view
from pipeline.domain import CATALOG

router = APIRouter(tags=["actions"])


@router.get("/actions")
def actions() -> list[ActionView]:
    """Each action with its kind (task: the pipeline does it; wait: an actor), the queue of its tasks and what it
    needs and gives. A cycle (`action: "cycle"`) isn't in the catalog: it groups stages and its last one is
    review.score."""
    return [action_view(a) for a in CATALOG.values()]
