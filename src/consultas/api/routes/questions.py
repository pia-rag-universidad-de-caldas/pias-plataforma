"""POST /search and POST /ask: the chunks closest to a question, and the answer that cites them."""

import logging

from fastapi import APIRouter

from consultas.api.bodies import against, attachments, llm_options
from consultas.api.dependencies import Asking
from consultas.api.responses import CONFLICT, DOWN, INVALID, NOT_FOUND, REFUSED
from consultas.api.schemas import AnswerView, NewQuestion, NewSearch, SecondsView
from consultas.models import Question, Source

LOG = logging.getLogger(__name__)
router = APIRouter(tags=["questions"])


@router.post("/search", responses=DOWN | INVALID | NOT_FOUND | CONFLICT | REFUSED)
def search(asker: Asking, body: NewSearch) -> list[Source]:
    """The chunks closest to the question, best first, with their cosine score; no LLM and no min_score. The question
    is embedded with the active model of embeddings (with `against`, the experiment's model, or `embeddings_model`)
    and searched in that model's index: empty if nothing was embedded with it yet. Each attachment searches too (a
    document by its pieces, read by POST /parsing/preview; an image by its description, from a vision model of llm),
    joined by best score."""
    found = asker.search(body.question or "", body.k, against(body.against), attachments(body.attachments))
    return found.sources


@router.post("/ask", responses=DOWN | INVALID | NOT_FOUND | CONFLICT | REFUSED)
def ask(asker: Asking, body: NewQuestion) -> AnswerView:
    """The answer with its sources (the chunks over min_score, numbered as the answer cites them). If none passes, it
    says it found nothing and the LLM isn't called. Without `chat`, a new one; with it, its last turns go to the LLM.
    The question, its answer and its sources are stored together, or nothing is (a module down: 503, saying which).
    With `attachments` (documents and images), it answers what in the official documents is similar to them: they
    never enter the corpus, and the question keeps only their names and types. An image needs a vision model
    downloaded in llm (503 saying which to pull); the answer sees it too if its model has vision."""
    question = Question(
        body.question or "",
        body.k,
        body.chat,
        llm_options(body.llm),
        against(body.against),
        attachments(body.attachments),
    )
    answer = asker.ask(question)
    LOG.info(
        "question %s of chat %s: %d sources, found=%s, %d attachments, %.1f s search, %.1f s answer%s",
        answer.consulta,
        answer.chat,
        len(answer.sources),
        answer.found,
        len(answer.attachments),
        answer.seconds.search,
        answer.seconds.answer,
        " (laboratory)" if answer.laboratory else "",
    )
    return AnswerView(
        answer.answer,
        answer.sources,
        answer.chat,
        answer.consulta,
        answer.model,
        answer.found,
        SecondsView(answer.seconds.search, answer.seconds.answer),
        answer.laboratory,
        answer.attachments,
        answer.courses,
    )
