"""POST /runs (a run in line: one at a time), GET /runs, GET /runs/{id} and DELETE /runs/{id}."""

from uuid import uuid4

from fastapi import APIRouter, HTTPException, status

from common.api import Error
from common.clock import now
from parsing.adapters.docling_parser import MISSING
from parsing.api.dependencies import DocumentParser, Queue, Raws, Registry, Settings, StoredRuns
from parsing.api.history import save, stored_run, stored_runs
from parsing.api.schemas import NewRun
from parsing.api.work_queue import LINE_FULL
from parsing.api.worker import launch
from parsing.config import PARSING, PARSING_VERSION
from parsing.domain import Check, fingerprint
from parsing.models import DocumentError, DocumentResult, Parser, ParsingRequest, ParsingRun, RunStatus, SinkError

router = APIRouter(tags=["runs"])

NO_DOCLING = "Docling is not installed (uv sync --extra parse): without it there is no fingerprint to compare"


def current(parser: Parser) -> str:
    """The fingerprint a parsing has now; 503 without Docling (its version is part of it)."""
    docling = parser.version()
    if docling is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, NO_DOCLING)
    return fingerprint(PARSING, PARSING_VERSION, docling)


@router.post(
    "/runs",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        409: {"model": Error, "description": "the line is full"},
        422: {"model": Error, "description": "invalid body (an unknown key, a sha256 that isn't one...)"},
        503: {"model": Error, "description": "Docling is not installed (uv sync --extra parse)"},
    },
)
def start_run(
    settings: Settings, registry: Registry, queue: Queue, parser: DocumentParser, raws: Raws, new: NewRun
) -> ParsingRun:
    """Puts a run in line and answers at once (`queued` if another one is running); follow it with GET /runs/{id} or
    GET /processes. Each sha256 is read from its RAW in data, parsed with the fixed configuration (GET /config) and
    written as PIAA → JSON → RAW in one POST /data/batch; the ones already parsed with the same fingerprint are
    skipped (`redo` parses them again) and a partial one resumes from its pending pages. Without `sha256s`, every
    current RAW still to parse (with `redo`, every current one), as data has them when the run is queued."""
    if not parser.available():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, MISSING)
    if queue.full:
        raise HTTPException(status.HTTP_409_CONFLICT, LINE_FULL)
    found = current(parser)
    if new.sha256s:
        sha256s = Check.unique(new.sha256s)
    else:
        sha256s = [state.sha256 for state in Check.pending(raws.all_states(), found, new.redo)]
    run = ParsingRun(
        id=uuid4().hex[:12],
        status=RunStatus.QUEUED,
        requested=now(),
        fingerprint=found,
        simulate=new.simulate,
        redo=new.redo,
        documents=[DocumentResult(sha256) for sha256 in sha256s],
    )
    registry.add(run)
    launch(queue, registry, run.id, settings.session, parser, ParsingRequest(sha256s, new.redo, new.simulate))
    return registry.get(run.id) or run


@router.get("/runs")
def list_runs(registry: Registry, stored: StoredRuns) -> list[ParsingRun]:
    """Every run, past server sessions included, newest first. If data doesn't answer, those of this session."""
    live = registry.all()
    known = {run.id for run in live}
    try:
        past = [run for run in stored_runs(stored) if run.id not in known]
    except (SinkError, DocumentError):
        return live
    return sorted([*live, *past], key=lambda run: run.requested, reverse=True)


@router.get("/runs/{id}", responses={404: {"model": Error, "description": "no run with that id"}})
def read_run(registry: Registry, stored: StoredRuns, id: str) -> ParsingRun:
    run = registry.get(id) or stored_run(stored, id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"there is no run with id {id!r}")
    return run


@router.delete(
    "/runs/{id}",
    responses={
        404: {"model": Error, "description": "no run with that id in this session"},
        409: {"model": Error, "description": "it isn't waiting in line (it runs or it ended)"},
    },
)
def cancel_run(registry: Registry, queue: Queue, stored: StoredRuns, id: str) -> ParsingRun:
    """Takes a queued run out of the line; one that runs or ended stays as it is."""
    run = registry.get(id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"there is no run with id {id!r} in this session")
    if not queue.cancel(id):
        raise HTTPException(status.HTTP_409_CONFLICT, f"the run {id!r} isn't waiting in line: it is {run.status}")
    registry.cancel(id)
    cancelled = registry.get(id) or run
    save(stored, cancelled)
    registry.on_done()
    return cancelled
