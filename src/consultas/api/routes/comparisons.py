"""POST /compare, GET /comparisons[/{id}], DELETE /comparisons/{id} (feature 060): one question to up to four panels,
each with its target, embeddings model and LLM, kept as one comparison."""

import logging

from fastapi import APIRouter, HTTPException, status

from consultas.api.bodies import against, attachments, llm_options, sent_against
from consultas.api.dependencies import Comparing, Comparisons
from consultas.api.responses import CONFLICT, DOWN, INVALID, REFUSED, error
from consultas.api.schemas import ComparisonView, NewComparison, PanelView
from consultas.models import Comparison, ComparisonRequest, ComparisonSummary, Panel, PanelStatus

LOG = logging.getLogger(__name__)
router = APIRouter(tags=["comparisons"])
MISSING = error(404, "no comparison, or no embeddings experiment, with that id")


def _missing(id: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"there is no comparison {id!r}")


def _view(comparison: Comparison) -> ComparisonView:
    panels = [
        PanelView(p.index, p.label, sent_against(p.against), p.status, p.error, p.answer) for p in comparison.panels
    ]
    return ComparisonView(comparison.id, comparison.question, comparison.created, panels)


@router.post("/compare", responses=DOWN | INVALID | MISSING | CONFLICT | REFUSED)
def compare(comparer: Comparing, body: NewComparison) -> ComparisonView:
    """The question to each panel, in order and one at a time; each one answers as POST /ask would (its own `against`,
    `llm` and `k`), without a chat. First everything is checked (llm admits each model, embeddings serves each model
    and has each experiment finished, the attachments): 422/404/409 without running any. The attachments are read and
    described once and every panel reuses them. A panel that fails keeps `status: error` with its message and the
    others go on; data down is 503 and nothing is stored. The comparison and the questions of its panels are stored
    together."""
    request = ComparisonRequest(
        body.question or "",
        tuple(
            Panel(p.label or f"Panel {i + 1}", against(p.against), llm_options(p.llm), p.k)
            for i, p in enumerate(body.panels)
        ),
        attachments(body.attachments),
    )
    comparison = comparer.compare(request)
    failed = sum(p.status is PanelStatus.ERROR for p in comparison.panels)
    LOG.info("comparison %s: %d panels, %d failed", comparison.id, len(comparison.panels), failed)
    return _view(comparison)


@router.get("/comparisons", responses=DOWN)
def list_comparisons(comparisons: Comparisons) -> list[ComparisonSummary]:
    """The newest first: the question, how many panels and their LLMs."""
    return comparisons.comparisons()


@router.get("/comparisons/{id}", responses=DOWN | error(404, "no comparison with that id"))
def read_comparison(comparisons: Comparisons, id: str) -> ComparisonView:
    """As POST /compare answered it, with the chunks each panel cited."""
    found = comparisons.detail(id)
    if found is None:
        raise _missing(id)
    return _view(found)


@router.delete(
    "/comparisons/{id}", status_code=status.HTTP_204_NO_CONTENT, responses=DOWN | error(404, "no comparison")
)
def delete_comparison(comparisons: Comparisons, id: str) -> None:
    """The comparison and the questions of its panels; the chunks they cite stay."""
    if not comparisons.delete(id):
        raise _missing(id)
