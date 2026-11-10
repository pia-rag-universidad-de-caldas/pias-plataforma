"""Laboratory: POST/GET /experiments, GET/DELETE /experiments/{id} and POST /experiments/{id}/apply. An experiment
embeds the chunks (EXP_CHUNK) of a finished chunking experiment with a model and a limit to try, apart from the
official vectors; the pipeline's laboratory scores the pair (chunking + embeddings). Its record is an EXP_EMBEDDINGS
node, linked to the chunking experiment (EXP_USA)."""

from dataclasses import replace
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response, status

from common.clock import now
from embeddings.adapters import MISSING, HttpSession
from embeddings.api.dependencies import Config, Embedding, Queue, Registry, Settings, Source, StoredRuns, Vectors
from embeddings.api.history import detail, stored_run, stored_runs
from embeddings.api.responses import DOWN, INVALID, error
from embeddings.api.routes.config import config_view
from embeddings.api.routes.runs import SIMULATION
from embeddings.api.schemas import ConfigView, NewExperiment
from embeddings.api.work_queue import LINE_FULL
from embeddings.api.worker import launch
from embeddings.domain import ExperimentRunner, RunEvents, UnfinishedExperiment, UnknownExperiment
from embeddings.models import (
    DocumentError,
    EmbeddingRun,
    ExperimentRequest,
    RunKind,
    RunProgress,
    RunStatus,
    UpstreamDown,
)

router = APIRouter(prefix="/experiments", tags=["experiments"])
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
    | error(409, "the line is full, or the chunking experiment didn't finish")
    | {200: {"model": EmbeddingRun, "description": "simulate: what it would do, nothing stored"}},
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
) -> EmbeddingRun:
    """Puts the experiment in line and answers at once (`queued` if something else runs). The chunking experiment
    must be finished; each of its chunks gets an EXP_EMBED of this experiment with its vector (feature 055: two
    experiments over the same chunks keep a vector each). A chunk longer than the limit fails its document."""
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
        return replace(run, id=SIMULATION, status=RunStatus.FINISHED, finished=now(), progress=progress)
    stored.save(EXPERIMENT, id, run.status.value, run.requested, detail(run))  # before answering: GET finds it
    stored.link(id, request.chunking_experiment)
    registry.add(run)

    def work(session: HttpSession, events: RunEvents) -> RunProgress:
        return ExperimentRunner.run(
            session.source, session.vectors, embedder, config, request.chunking_experiment, False, events
        )

    launch(queue, registry, id, settings.session, work)
    return registry.get(id) or run


@router.get("", responses=DOWN)
def list_experiments(registry: Registry, stored: StoredRuns) -> list[EmbeddingRun]:
    """Every experiment, past server sessions included, newest first. If data doesn't answer, those of this one."""
    live = registry.all(EXPERIMENT)
    known = {run.id for run in live}
    try:
        past = [run for run in stored_runs(stored, EXPERIMENT) if run.id not in known]
    except (UpstreamDown, DocumentError):
        return live
    return sorted([*live, *past], key=lambda run: run.requested, reverse=True)


@router.get("/{id}", responses=DOWN | NOT_FOUND)
def read_experiment(registry: Registry, stored: StoredRuns, id: str) -> EmbeddingRun:
    """Its configuration, progress and failures; `embedded` says which sha256s got vectors."""
    return _found(registry, stored, id)


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=DOWN | NOT_FOUND | error(409, "it is running"),
)
def delete_experiment(registry: Registry, queue: Queue, vectors: Vectors, stored: StoredRuns, id: str) -> None:
    """Deletes the experiment and its vectors (its EXP_EMBED, feature 055: never another experiment's); the chunks and
    their text stay. One in line leaves the line."""
    _found(registry, stored, id)
    if queue.active == id:
        raise HTTPException(status.HTTP_409_CONFLICT, "the experiment is running")
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
