"""Runs: /runs to start, read, answer, resume and cancel them."""

from uuid import uuid4

from fastapi import APIRouter, Response, status

from pipeline.api.dependencies import Runner, Store
from pipeline.api.executor import now
from pipeline.api.schemas import CompleteBody, DecisionBody, EventBody, NewRun, RunStarted, RunSummary, RunView, error
from pipeline.api.templates import find
from pipeline.api.views import run_summary, run_view
from pipeline.domain import Engine
from pipeline.models import (
    FILE_BATCH,
    Completion,
    Decision,
    DecisionKind,
    EventRequest,
    NotFoundError,
    RunRequest,
    RunStatus,
    StageKind,
    selection_from_json,
)

router = APIRouter(prefix="/runs", tags=["runs"])

_NOT_FOUND = error(404, "there is no run with that id")
_CONFLICT = error(409, "the run isn't waiting there, for that actor (or the cycle is exhausted)")
_INVALID = error(422, "malformed body")
_DOWN = error(503, "ingesta, chunking or data didn't answer")


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    responses={200: {"model": RunStarted, "description": "simulate: the batch the first selection would take"}}
    | error(404, "there is no template with that id")
    | error(422, "a template that can't run, malformed files or params")
    | _DOWN,
)
def start_run(store: Store, runner: Runner, new: NewRun, response: Response) -> RunStarted:
    """Creates the run with a copy of the template and starts it in the background (202). With `simulate`, only
    checks it and answers the batch its first stage would select, if it is ingesta.select (200, nothing stored)."""
    files = None if new.files is None else selection_from_json(new.files)
    template = find(store, new.template)
    request = RunRequest(new.template, new.name, files, dict(new.params))
    run = Engine.new(uuid4().hex[:12], request, template, now())
    if new.simulate:
        response.status_code = status.HTTP_200_OK
        started = Engine.start(run, now())
        step = Engine.next(started)
        batch: list[str] = []
        if step is not None and step.kind == StageKind.TASK and step.action.name == "ingesta.select":
            context = Engine.context(started, runner.modules, store)
            selected = step.action.run(context).artifacts.get(FILE_BATCH)
            batch = [str(s) for s in selected] if isinstance(selected, list) else []
        return RunStarted("simulated", None, batch)
    run = runner.launch(run)
    return RunStarted(runner.status(run).value, run_view(run, runner.status(run)), [])


@router.get("")
def list_runs(store: Store, runner: Runner, status: RunStatus | None = None) -> list[RunSummary]:
    """Newest first; `?status=waiting` (or any other) filters."""
    runs = sorted(store.runs(), key=lambda r: r.created, reverse=True)
    summaries = [run_summary(r, runner.status(r)) for r in runs]
    return [s for s in summaries if status is None or s.status == status.value]


@router.get("/{id}", responses=_NOT_FOUND)
def read_run(store: Store, runner: Runner, id: str) -> RunView:
    run = store.run(id)
    if run is None:
        raise NotFoundError(f"there is no run {id}")
    return run_view(run, runner.status(run))


@router.post("/{id}/stages/{stage}/decision", responses=_NOT_FOUND | _CONFLICT | _INVALID | _DOWN)
def decide(runner: Runner, id: str, stage: str, body: DecisionBody) -> RunView:
    """The cycle's actor at its review (`stage`: the cycle or its review stage): `retry` with `next`, or `approve`
    (`iteration`, the last by default). `score` is stored on the iteration's experiment first."""
    decision = Decision(DecisionKind(body.decision), body.actor, body.iteration, dict(body.next), body.score)
    run = runner.decide(id, stage, decision)
    return run_view(run, runner.status(run))


@router.post("/{id}/stages/{stage}/complete", responses=_NOT_FOUND | _CONFLICT | _INVALID | _DOWN)
def complete(runner: Runner, id: str, stage: str, body: CompleteBody) -> RunView:
    """The actor of an external stage is done: `result` fills what the stage gives; `error` fails the run."""
    run = runner.complete(id, stage, Completion(body.actor, body.result, body.error))
    return run_view(run, runner.status(run))


@router.post("/{id}/events", responses=_NOT_FOUND | _DOWN)
def add_event(runner: Runner, id: str, body: EventBody) -> RunView:
    """An actor's note on the run (a call to embeber or modelscenter inside a cycle...); the state doesn't change."""
    run = runner.event(id, EventRequest(body.actor, body.kind, body.detail))
    return run_view(run, runner.status(run))


@router.post("/{id}/resume", responses=_NOT_FOUND | error(409, "the run isn't failed nor interrupted") | _DOWN)
def resume(runner: Runner, id: str) -> RunView:
    """Runs a failed or interrupted run again from the stage it stopped at (that stage is repeated)."""
    run = runner.resume(id)
    return run_view(run, runner.status(run))


@router.post("/{id}/cancel", responses=_NOT_FOUND | error(409, "the run already ended") | _DOWN)
def cancel(runner: Runner, id: str) -> RunView:
    run = runner.cancel(id)
    return run_view(run, runner.status(run))
