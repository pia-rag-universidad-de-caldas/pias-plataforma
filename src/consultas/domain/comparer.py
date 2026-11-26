"""Comparer: one question to up to four panels (feature 060), each with its target, its embeddings model and its LLM,
kept as one COMPARACION.

Everything that can be checked cheaply is checked before any panel runs (the LLM models llm admits, the embeddings
models and experiments, the attachments): a mistake costs nothing. The attachments are read once and every panel
reuses them. The panels run in order, one at a time (a local Ollama, one GPU). A panel that fails (llm without the
model, embeddings refusing something) keeps its error and the others go on; data down stops the comparison before
anything is stored: without data no panel could be kept."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from common.clock import now
from consultas.config import ATTACHMENT_QUESTION, FINISHED_EXPERIMENT
from consultas.models import (
    Comparison,
    ComparisonRequest,
    ComparisonStore,
    Conflict,
    ConsultasConfig,
    ConsultasError,
    DataDown,
    EmbeddingsCatalog,
    InvalidQuestion,
    NotFound,
    Panel,
    PanelAnswer,
    PanelResult,
    PanelStatus,
    Prepared,
    Question,
)

from .active_config import resolve
from .asker import Asker
from .comparisons import Asked, comparison_batch


def _new_id() -> str:
    return uuid.uuid4().hex


def _tagged(name: str) -> str:
    """llm's names: `llama3.1` is `llama3.1:latest`."""
    return name if ":" in name else f"{name}:latest"


@dataclass
class Comparer:
    asker: Asker
    catalog: EmbeddingsCatalog
    store: ComparisonStore
    new_id: Callable[[], str] = _new_id
    today: Callable[[], str] = field(default=now)

    def _check_llm(self, request: ComparisonRequest) -> None:
        asked = {p.llm.model for p in request.panels if p.llm.model is not None}
        if not asked or self.asker.vision is None:  # without llm's models, llm itself says it to each panel
            return
        admitted = {_tagged(m.name) for m in self.asker.vision.models()}
        unknown = sorted(name for name in asked if _tagged(name) not in admitted)
        if unknown:
            raise InvalidQuestion(f"llm doesn't admit {', '.join(unknown)} (GET /llm/models)")

    def _check_embeddings(self, request: ComparisonRequest) -> None:
        targets = [p.against for p in request.panels if p.against is not None]
        models = {t.embeddings_model for t in targets if t.embeddings_model is not None}
        if models:
            served = {m.name for m in self.catalog.models()}
            unknown = sorted(models - served)
            if unknown:
                raise InvalidQuestion(f"embeddings doesn't serve {', '.join(unknown)} (GET /embeddings/models)")
        for id in sorted({t.embeddings_experiment for t in targets if t.embeddings_experiment is not None}):
            experiment = self.asker.vectors.experiment(id)
            if experiment is None:
                raise NotFound(f"embeddings has no experiment {id!r}")
            if experiment.status != FINISHED_EXPERIMENT:
                raise Conflict(f"the embeddings experiment {id!r} is {experiment.status}, not finished")

    def check(self, request: ComparisonRequest) -> None:
        """What every panel needs, before any of them runs."""
        if not request.panels:
            raise InvalidQuestion("a comparison needs some panel")
        if not request.text.strip() and not request.attachments:
            raise InvalidQuestion("a question needs its text or some attachment")
        self._check_llm(request)
        self._check_embeddings(request)

    def _run(
        self, index: int, panel: Panel, request: ComparisonRequest, prepared: Prepared, config: ConsultasConfig
    ) -> Asked:
        question = Question(request.text, panel.k, None, panel.llm, panel.against, request.attachments)
        consulta = self.new_id()
        try:
            response = self.asker.respond(question, prepared=prepared, config=config)
        except DataDown:
            raise  # without data nothing of the comparison can be kept: it stops here
        except ConsultasError as e:  # this panel's: the others still answer
            failed = PanelResult(index, panel.label, panel.against, panel.llm, panel.k, PanelStatus.ERROR, str(e))
            return Asked(failed)
        answer = PanelAnswer(
            response.answer,
            response.sources,
            consulta,
            response.model,
            response.found,
            response.seconds,
            response.laboratory,
            response.attachments,
            response.courses,
        )
        result = PanelResult(index, panel.label, panel.against, panel.llm, panel.k, PanelStatus.OK, answer=answer)
        return Asked(result, response)

    def compare(self, request: ComparisonRequest) -> Comparison:
        self.check(request)
        config = resolve(self.asker.config)
        prepared = self.asker.prepare(request.attachments)
        asked = [self._run(i, panel, request, prepared, config) for i, panel in enumerate(request.panels)]
        id, created = self.new_id(), self.today()
        question = request.text if request.text.strip() else ATTACHMENT_QUESTION
        self.store.save(comparison_batch(id, question, created, asked))
        return Comparison(id, question, created, [a.result for a in asked])
