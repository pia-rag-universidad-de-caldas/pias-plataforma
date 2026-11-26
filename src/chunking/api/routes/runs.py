"""The official chunking (feature 045): POST /runs chunks with the active configuration the given parsed documents, or
what is missing (one page of it, or all), and replaces what hung from each JSON; GET /runs[/{id}], DELETE /runs/{id},
POST /runs/{id}/cancel (feature 056) and POST /runs/{id}/resume. A document is never chunked twice with the same
configuration over the same parse."""

from dataclasses import dataclass, field, replace
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import Field

from chunking.adapters.docling_chunkers import MISSING
from chunking.api.dependencies import Config, DocumentChunker, Queue, Runs, Settings, Store, StoredRuns
from chunking.api.experiments.responses import DOWN, INVALID, Responses
from chunking.api.runs import launch, record
from chunking.api.schemas import STRICT, Sha256
from chunking.api.work_queue import LINE_FULL
from chunking.config import MAX_PER_PAGE
from chunking.domain import Parameters, RunRunner
from chunking.models import (
    RESUMABLE,
    ChunkingRun,
    DocumentError,
    NoConfiguration,
    RunProgress,
    RunStatus,
    SinkError,
)
from common.api import Error
from common.clock import now

router = APIRouter(prefix="/runs", tags=["runs"])
NO_RUN: Responses = {404: {"model": Error, "description": "no run with that id"}}


@dataclass(frozen=True)
class NewRun:
    """`sha256s`, or what is missing with the active configuration: one page of it (`page`, `per_page`) or all."""

    __pydantic_config__ = STRICT

    sha256s: list[Sha256] = field(default_factory=list)
    page: Annotated[int | None, Field(ge=1)] = None
    per_page: Annotated[int | None, Field(ge=1, le=MAX_PER_PAGE)] = None
    simulate: bool = False  # only count what would be chunked, skipped and unparsed


def _found(runs: Runs, stored: StoredRuns, id: str) -> ChunkingRun:
    found = runs.get(id) or stored.run(id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"there is no run with id {id!r}")
    return found


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    responses=DOWN
    | INVALID
    | {
        200: {"model": ChunkingRun, "description": "simulate: what would be done, nothing written"},
        409: {"model": Error, "description": "the line is full, or there is no configuration to chunk with"},
        503: {"model": Error, "description": "docling-core is not installed (uv sync --extra chunk), or data is down"},
    },
)
def start_run(
    settings: Settings,
    store: Store,
    config: Config,
    runs: Runs,
    queue: Queue,
    chunker: DocumentChunker,
    new: NewRun,
    response: Response,
) -> ChunkingRun:
    """Chunks with the active configuration (GET /config), read now: changing it later doesn't change this run. With
    `sha256s`, those; without, what is missing with it (GET /data/progress/chunking?fingerprint=), taken when its turn
    comes: one page (`page`, `per_page`) or all. For each document, its SECCION/FRAGMENTOS are replaced:
    (:JSON)-[:TIENE_SECCION]->(:SECCION)-[:TIENE_FRAGMENTO]->(:FRAGMENTOS). One already chunked with the same
    configuration over the same parse is skipped, never chunked twice; one without a parse is `sin_parseo`. Answers at
    once (202, `queued` if something else runs); follow it with GET /runs/{id}: `chunked` are the sha256s to hand to
    embeddings (the skipped ones too)."""
    if new.sha256s and (new.page is not None or new.per_page is not None):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "give sha256s or page/per_page, not both")
    if queue.full and not new.simulate:
        raise HTTPException(status.HTTP_409_CONFLICT, LINE_FULL)
    try:
        parameters, active = Parameters.active(config.stored(), chunker.version() or "")
    except NoConfiguration as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    page = new.page or (1 if new.per_page is not None else None)
    run = ChunkingRun(
        id=uuid4().hex[:12],
        status=RunStatus.QUEUED,
        requested=now(),
        simulate=new.simulate,
        parameters=parameters,
        sha256s=list(dict.fromkeys(new.sha256s)),
        frozen=bool(new.sha256s),
        page=page,
        per_page=new.per_page if page is not None else None,
        experiment=active.experiment,
    )
    if new.simulate:
        sha256s = run.sha256s or store.missing(parameters.fingerprint, run.page, run.per_page)
        outcome = RunRunner.run(store, chunker, sha256s, parameters, active.experiment, now, simulate=True)
        response.status_code = status.HTTP_200_OK
        return replace(
            run,
            status=RunStatus.FINISHED,
            sha256s=sha256s,
            frozen=True,
            progress=outcome.progress,
            failures=outcome.failures,
            chunked=outcome.chunked,
            finished=now(),
        )
    if not chunker.available():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, MISSING)
    runs.add(run)
    launch(queue, runs, run, settings.session, chunker)
    return runs.get(run.id) or run


@router.get("")
def list_runs(runs: Runs, stored: StoredRuns) -> list[ChunkingRun]:
    """Every run, past server sessions included, newest first. If data doesn't answer, those of this session."""
    live = runs.all()
    known = {r.id for r in live}
    try:
        past = [r for r in stored.runs() if r.id not in known]
    except (SinkError, DocumentError):
        return live
    return sorted([*live, *past], key=lambda r: r.requested, reverse=True)


@router.get("/{id}", responses=NO_RUN)
def read_run(runs: Runs, stored: StoredRuns, id: str) -> ChunkingRun:
    return _found(runs, stored, id)


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=NO_RUN | {409: {"model": Error, "description": "it is running or already ended"}},
)
def cancel_run(settings: Settings, runs: Runs, queue: Queue, id: str) -> None:
    """Takes a run out of the line, before it runs; it ends `interrupted` (it can be resumed)."""
    if runs.get(id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"there is no run with id {id!r} in this session")
    if not queue.cancel(id):
        raise HTTPException(status.HTTP_409_CONFLICT, "the run isn't waiting in line")
    runs.cancel(id)
    record(runs, id, settings.session)
    runs.on_done()


@router.post("/{id}/cancel", responses=NO_RUN | {409: {"model": Error, "description": "the run already ended"}})
def stop_run(settings: Settings, runs: Runs, queue: Queue, id: str) -> ChunkingRun:
    """Cancels a run (feature 056): one in line leaves it (as DELETE); one that runs finishes the document it is on,
    keeps what it chunked and ends `interrupted` (`cancel_requested` until then). Either way POST /runs/{id}/resume
    goes on with its list, skipping what is done."""
    run = runs.get(id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"there is no run with id {id!r} in this session")
    if queue.cancel(id):
        runs.cancel(id)
        record(runs, id, settings.session)
        runs.on_done()
        return runs.get(id) or run
    asked = runs.request_cancel(id)
    if asked is None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"the run already ended: it is {run.status.value}")
    return asked


@router.post(
    "/{id}/resume",
    status_code=status.HTTP_202_ACCEPTED,
    responses=NO_RUN
    | DOWN
    | {
        409: {
            "model": Error,
            "description": "it isn't partial, failed or interrupted, the active configuration changed, or the line is"
            " full",
        },
        503: {"model": Error, "description": "docling-core is not installed (uv sync --extra chunk), or data is down"},
    },
)
def resume_run(
    settings: Settings,
    config: Config,
    runs: Runs,
    stored: StoredRuns,
    queue: Queue,
    chunker: DocumentChunker,
    id: str,
) -> ChunkingRun:
    """Goes over the documents of the run again, with its configuration: what is already chunked is skipped, so only
    what failed or wasn't reached is chunked. Only of a `partial`, `failed` or `interrupted` run, and only while the
    active configuration is still the one it was asked with (if not, what it did doesn't count for the new one: start a
    new run). The same id: it goes back in line and ends with the state of the whole run."""
    run = _found(runs, stored, id)
    if runs.alive(id) or run.status not in RESUMABLE or run.simulate:
        raise HTTPException(status.HTTP_409_CONFLICT, f"the run is {run.status.value}: there is nothing to resume")
    try:
        active = Parameters.active(config.stored(), chunker.version() or "")[0]
    except NoConfiguration as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    if active.fingerprint != run.parameters.fingerprint:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "the active configuration changed since this run: what it did doesn't count for the new one; start a new"
            " run (POST /runs)",
        )
    if queue.full:
        raise HTTPException(status.HTTP_409_CONFLICT, LINE_FULL)
    if not chunker.available():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, MISSING)
    again = replace(
        run,
        status=RunStatus.QUEUED,
        started=None,
        finished=None,
        error=None,
        progress=RunProgress(),
        failures=[],
        resumed=run.resumed + 1,
        cancel_requested=False,
    )
    runs.add(again)
    launch(queue, runs, again, settings.session, chunker)
    return runs.get(id) or again
