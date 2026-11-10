"""Production: POST /runs (a run in line: one at a time), GET /runs, GET /runs/{id} and DELETE /runs/{id}. A run
embeds the official chunks (FRAGMENTOS) of the given chunked documents with the active configuration, resolved when it
is queued: changing it afterwards doesn't touch a run that waits or goes."""

from dataclasses import replace
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response, status

from common.clock import now
from embeddings.adapters import MISSING, HttpSession
from embeddings.api.dependencies import Config, Embedding, Queue, Registry, Settings, Source, StoredRuns, Vectors
from embeddings.api.history import save, stored_run, stored_runs
from embeddings.api.responses import DOWN, INVALID, error
from embeddings.api.schemas import NewRun
from embeddings.api.work_queue import LINE_FULL
from embeddings.api.worker import launch
from embeddings.domain import RunEvents, Runner, resolve, run_config
from embeddings.models import DocumentError, EmbeddingRun, RunKind, RunProgress, RunRequest, RunStatus, UpstreamDown

router = APIRouter(prefix="/runs", tags=["runs"])
RUN = RunKind.RUN
SIMULATION = "simulation"  # the id of what a simulation answers: nothing was queued nor stored


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    responses=DOWN
    | INVALID
    | error(409, "the line is full")
    | {200: {"model": EmbeddingRun, "description": "simulate: what it would do, nothing stored"}},
)
def start_run(
    settings: Settings,
    registry: Registry,
    queue: Queue,
    embedder: Embedding,
    config: Config,
    source: Source,
    vectors: Vectors,
    new: NewRun,
    response: Response,
) -> EmbeddingRun:
    """Puts a run in line and answers at once (`queued` if another one is running); follow it with GET /runs/{id} or
    GET /processes. Each document must be chunked (estado_chunking `fragmentado`); one whose chunks and model didn't
    change since it was embedded is `unchanged` (`force` embeds it again). A chunk longer than the limit makes its
    document fail: it is never cut. `embedded` lists the sha256s whose chunks have vectors when it ends. With `model`
    (another served model), the vectors go next to the active model's, in its own property and index: the chat keeps
    using the active one until PUT /config changes it (feature 055)."""
    if not embedder.available():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, MISSING)
    if queue.full and not new.simulate:
        raise HTTPException(status.HTTP_409_CONFLICT, LINE_FULL)
    active = run_config(resolve(config), new.model)  # another model: 422 if it isn't served
    request = RunRequest(list(dict.fromkeys(new.sha256s)), new.simulate, new.force, new.model)
    run = EmbeddingRun(
        id=uuid4().hex[:12],
        kind=RUN,
        status=RunStatus.QUEUED,
        requested=now(),
        config=active,
        sha256s=request.sha256s,
        simulate=new.simulate,
        force=new.force,
    )
    if new.simulate:  # synchronous: it reads every chunk and counts its tokens, but calculates and writes nothing
        response.status_code = status.HTTP_200_OK
        progress = Runner.run(source, vectors, embedder, active, request)
        return replace(run, id=SIMULATION, status=RunStatus.FINISHED, finished=now(), progress=progress)
    registry.add(run)

    def work(session: HttpSession, events: RunEvents) -> RunProgress:
        return Runner.run(session.source, session.vectors, embedder, active, request, events)

    launch(queue, registry, run.id, settings.session, work)
    return registry.get(run.id) or run


@router.get("", responses=DOWN)
def list_runs(registry: Registry, stored: StoredRuns) -> list[EmbeddingRun]:
    """Every run, past server sessions included, newest first. If data doesn't answer, those of this session."""
    live = registry.all(RUN)
    known = {run.id for run in live}
    try:
        past = [run for run in stored_runs(stored, RUN) if run.id not in known]
    except (UpstreamDown, DocumentError):
        return live
    return sorted([*live, *past], key=lambda run: run.requested, reverse=True)


@router.get("/{id}", responses=DOWN | error(404, "no run with that id"))
def read_run(registry: Registry, stored: StoredRuns, id: str) -> EmbeddingRun:
    run = registry.get(id, RUN) or stored_run(stored, RUN, id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"there is no run with id {id!r}")
    return run


@router.delete(
    "/{id}",
    responses=error(404, "no run with that id in this session") | error(409, "it isn't waiting in line"),
)
def cancel_run(registry: Registry, queue: Queue, stored: StoredRuns, id: str) -> EmbeddingRun:
    """Takes a queued run out of the line; one that runs or ended stays as it is."""
    run = registry.get(id, RUN)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"there is no run with id {id!r} in this session")
    if not queue.cancel(id):
        raise HTTPException(status.HTTP_409_CONFLICT, f"the run {id!r} isn't waiting in line: it is {run.status}")
    registry.cancel(id)
    cancelled = registry.get(id) or run
    save(stored, cancelled)
    registry.on_done()
    return cancelled
