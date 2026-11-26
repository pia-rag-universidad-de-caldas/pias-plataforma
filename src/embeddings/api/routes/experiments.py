"""Laboratory: POST/GET /experiments, GET/DELETE /experiments/{id} and POST /experiments/{id}/apply. An experiment
embeds the chunks (EXP_CHUNK) of a finished chunking experiment with a model and a limit to try, apart from the
official vectors; the pipeline's laboratory scores the pair (chunking + embeddings). Its record is an EXP_EMBEDDINGS
node, linked to the chunking experiment (EXP_USA)."""

import logging
from dataclasses import replace
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Response, status

from common.clock import now
from embeddings.adapters import MISSING, HttpSession
from embeddings.api.dependencies import Config, Embedding, Queue, Registry, Settings, Source, StoredRuns, Vectors
from embeddings.api.history import detail, stored_run, stored_runs
from embeddings.api.responses import DOWN, INVALID, error
from embeddings.api.routes.config import config_view
from embeddings.api.routes.runs import SIMULATION
from embeddings.api.schemas import ConfigView, ExperimentResume, ExperimentView, NewExperiment
from embeddings.api.work_queue import LINE_FULL
from embeddings.api.worker import launch
from embeddings.domain import ExperimentRunner, RunEvents, UnfinishedExperiment, UnknownExperiment
from embeddings.models import (
    ALIVE,
    DocumentError,
    EmbeddingRun,
    ExperimentRequest,
    RunKind,
    RunProgress,
    RunStatus,
    UpstreamDown,
)

router = APIRouter(prefix="/experiments", tags=["experiments"])
LOG = logging.getLogger(__name__)
EXPERIMENT = RunKind.EXPERIMENT
NOT_FOUND = error(404, "no experiment (or chunking experiment) with that id")


def _found(registry: Registry, stored: StoredRuns, id: str) -> EmbeddingRun:
    found = registry.get(id, EXPERIMENT) or stored_run(stored, EXPERIMENT, id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"there is no embeddings experiment with id {id!r}")
    return found


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    responses=DOWN
    | INVALID
    | NOT_FOUND
    | error(409, "the line is full, or the chunking experiment didn't end (finished or partial)")
    | {200: {"model": ExperimentView, "description": "simulate: what it would do, nothing stored"}},
)
def start_experiment(
    settings: Settings,
    registry: Registry,
    queue: Queue,
    embedder: Embedding,
    source: Source,
    vectors: Vectors,
    stored: StoredRuns,
    new: NewExperiment,
    response: Response,
) -> ExperimentView:
    """Puts the experiment in line and answers at once (`queued` if something else runs). The chunking experiment
    must have ended (finished or, feature 059, partial: what it chunked); each of its chunks gets an EXP_EMBED of
    this experiment with its vector (feature 055: two experiments over the same chunks keep a vector each, even with
    the same model). A chunk longer than the limit fails its document."""
    if not embedder.available():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, MISSING)
    if queue.full and not new.simulate:
        raise HTTPException(status.HTTP_409_CONFLICT, LINE_FULL)
    id = uuid4().hex[:12]
    request = ExperimentRequest(new.chunking_experiment, new.model, new.max_tokens, new.name, new.description)
    config = ExperimentRunner.config(request, id)  # InvalidLimit: 422
    try:
        ExperimentRunner.check(source, request.chunking_experiment)
    except UnknownExperiment as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    except UnfinishedExperiment as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    run = EmbeddingRun(
        id=id,
        kind=EXPERIMENT,
        status=RunStatus.QUEUED,
        requested=now(),
        config=config,
        chunking_experiment=request.chunking_experiment,
        name=request.name,
        description=request.description,
        simulate=new.simulate,
    )
    if new.simulate:
        response.status_code = status.HTTP_200_OK
        progress = ExperimentRunner.run(source, vectors, embedder, config, request.chunking_experiment, True)
        return ExperimentView.of(
            replace(run, id=SIMULATION, status=RunStatus.FINISHED, finished=now(), progress=progress)
        )
    stored.save(EXPERIMENT, id, run.status.value, run.requested, detail(run))  # before answering: GET finds it
    stored.link(id, request.chunking_experiment)
    registry.add(run)

    def work(session: HttpSession, events: RunEvents) -> RunProgress:
        return ExperimentRunner.run(
            session.source, session.vectors, embedder, config, request.chunking_experiment, False, events
        )

    launch(queue, registry, id, settings.session, work)
    return ExperimentView.of(registry.get(id) or run)


def _all(registry: Registry, stored: StoredRuns) -> list[EmbeddingRun]:
    live = registry.all(EXPERIMENT)
    known = {run.id for run in live}
    try:
        past = [run for run in stored_runs(stored, EXPERIMENT) if run.id not in known]
    except (UpstreamDown, DocumentError):
        return live
    return sorted([*live, *past], key=lambda run: run.requested, reverse=True)


@router.get("", responses=DOWN)
def list_experiments(
    registry: Registry,
    stored: StoredRuns,
    chunking_experiment: Annotated[
        str | None, Query(description="only those over the chunks of this chunking experiment (feature 059)")
    ] = None,
) -> list[ExperimentView]:
    """Every experiment, past server sessions included, newest first (or only those over one chunking experiment:
    several, one per model or even the same model twice, coexist). If data doesn't answer, those of this one."""
    found = _all(registry, stored)
    if chunking_experiment is not None:
        found = [run for run in found if run.chunking_experiment == chunking_experiment]
    return [ExperimentView.of(run) for run in found]


@router.get("/{id}", responses=DOWN | NOT_FOUND)
def read_experiment(registry: Registry, stored: StoredRuns, source: Source, id: str) -> ExperimentView:
    """Its configuration, model, dimensions, progress and failures; `embedded` says which sha256s got vectors;
    `pending` (feature 062), how many chunked documents of its chunking experiment still lack its vectors (None if
    data doesn't answer)."""
    run = _found(registry, stored, id)
    try:
        missing = source.experiment_missing(id)
    except (UpstreamDown, DocumentError):
        missing = None
    return ExperimentView.of(run, None if missing is None else len(missing))


@router.post(
    "/{id}/resume",
    status_code=status.HTTP_202_ACCEPTED,
    responses=DOWN
    | NOT_FOUND
    | error(
        409, "it is queued or running, its chunking experiment didn't end, nothing is missing, or the line is full"
    ),
)
def resume_experiment(
    settings: Settings,
    registry: Registry,
    queue: Queue,
    embedder: Embedding,
    source: Source,
    stored: StoredRuns,
    id: str,
    body: ExperimentResume | None = None,
) -> ExperimentView:
    """Feature 062: embeds, with its own model and limit, the chunked documents of its chunking experiment that don't
    have a vector of this experiment yet (added to it afterwards, chunked again, or left halfway); with `sha256s`,
    only those of them. The same id goes back in line; what it embedded stays."""
    if not embedder.available():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, MISSING)
    run = _found(registry, stored, id)
    if registry.get(id) is not None and run.status in ALIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, f"the experiment is {run.status}")
    chunking = run.chunking_experiment or ""
    try:
        ExperimentRunner.check(source, chunking)
    except UnknownExperiment as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e
    except UnfinishedExperiment as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    pending = ExperimentRunner.pending(source, id, chunking, body.sha256s if body else ())
    if not pending:
        raise HTTPException(status.HTTP_409_CONFLICT, "nothing is missing: every chunked document has its vectors")
    if queue.full:
        raise HTTPException(status.HTTP_409_CONFLICT, LINE_FULL)
    left = set(pending)
    kept = [sha256 for sha256 in run.embedded if sha256 not in left]
    start = RunProgress(total=len(kept) + len(pending), embedded=len(kept), chunks=run.progress.chunks)
    resumed = replace(
        run,
        status=RunStatus.QUEUED,
        started=None,
        finished=None,
        error=None,
        failures=[],
        embedded=kept,
        progress=start,
        cancel_requested=False,
        resumed=run.resumed + 1,
    )
    stored.save(EXPERIMENT, id, resumed.status.value, resumed.requested, detail(resumed))
    registry.add(resumed)
    config = run.config

    def work(session: HttpSession, events: RunEvents) -> RunProgress:
        return ExperimentRunner.run(
            session.source, session.vectors, embedder, config, chunking, False, events, pending, start
        )

    launch(queue, registry, id, settings.session, work)
    LOG.info("embeddings experiment %s resumed over %d documents", id, len(pending))
    return ExperimentView.of(registry.get(id) or resumed, len(pending))


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=DOWN | NOT_FOUND | error(409, "it is running, or (without force) a pipeline run links it"),
)
def delete_experiment(
    registry: Registry,
    queue: Queue,
    vectors: Vectors,
    stored: StoredRuns,
    id: str,
    force: Annotated[
        bool, Query(description="delete it even if a pipeline run links it (that run can't be saved again afterwards)")
    ] = False,
) -> None:
    """Deletes the experiment and its vectors (its EXP_EMBED, feature 055: never another experiment's); the chunks and
    their text stay. One in line leaves the line. 409 if, without `force`, a pipeline run links it (PIPE_USA)."""
    _found(registry, stored, id)
    if queue.active == id:
        raise HTTPException(status.HTTP_409_CONFLICT, "the experiment is running")
    linked = stored.linked_by(id)
    if linked and not force:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"the pipeline iterations {', '.join(linked)} link it: with force=true it is deleted anyway and those "
            "runs can't be saved again",
        )
    if linked:
        LOG.warning("embeddings experiment %s deleted with force: the pipeline iterations %s lose it", id, linked)
    queue.cancel(id)
    vectors.save(ExperimentRunner.cleared(id))  # before its record: replace_from needs the EXP_EMBEDDINGS
    stored.delete(EXPERIMENT, id)
    registry.remove(id)
    registry.on_done()


@router.post("/{id}/apply", responses=DOWN | NOT_FOUND | error(409, "the experiment didn't finish"))
def apply_experiment(registry: Registry, stored: StoredRuns, config: Config, id: str) -> ConfigView:
    """Copies the model and limit of a finished experiment to the active configuration. Nothing is embedded: that is
    the next POST /runs."""
    run = _found(registry, stored, id)
    if run.status is not RunStatus.FINISHED:
        raise HTTPException(status.HTTP_409_CONFLICT, f"the experiment is {run.status}")
    return config_view(ExperimentRunner.apply(config, run.config))
