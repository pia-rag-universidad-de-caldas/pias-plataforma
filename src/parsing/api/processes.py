"""What parsing has going on (as feature 039): the runs of this session and, read from the graph, those of the past."""

from collections.abc import Callable, Sequence
from datetime import datetime

from common.processes import History, ProcessFacts, ProcessSnapshot, ProcessState, describe
from parsing.models import DocumentError, ParsingRun, RunStatus, SinkError

from .registry import RunRegistry
from .work_queue import WorkQueue

MODULE = "parsing"
RUN = "run"
_STATE = {
    RunStatus.QUEUED: ProcessState.QUEUED,
    RunStatus.RUNNING: ProcessState.RUNNING,
    RunStatus.FINISHED: ProcessState.FINISHED,
    RunStatus.FAILED: ProcessState.FAILED,
    RunStatus.INTERRUPTED: ProcessState.INTERRUPTED,
    RunStatus.CANCELLED: ProcessState.CANCELLED,
}


def facts(run: ParsingRun, position: int | None) -> ProcessFacts:
    progress = run.progress
    return ProcessFacts(
        run.id,
        MODULE,
        RUN,
        "simulation" if run.simulate else "parsing run",
        _STATE[run.status],
        run.requested,
        started=run.started,
        finished=run.finished,
        position=position,
        strategies=(f"docling {run.fingerprint}",),
        done=progress.done,
        total=progress.total,
        counters={
            "parsed": progress.parsed,
            "partial": progress.partial,
            "errors": progress.errors,
            "skipped": progress.skipped,
            "missing": progress.missing,
        },
        error=run.error,
    )


class ParsingProcesses:
    def __init__(self, queue: WorkQueue, runs: RunRegistry, stored: Callable[[], Sequence[ParsingRun]]) -> None:
        self._queue, self._runs = queue, runs
        self._history = History(lambda: [facts(r, None) for r in stored()], (SinkError, DocumentError))
        runs.on_done = self._history.expire

    def snapshot(self, at: datetime) -> ProcessSnapshot:
        line = {id: place for place, id in enumerate(self._queue.waiting(), start=1)}
        session = self._runs.all()
        known = {r.id for r in session}
        stored, problem = self._history.current()
        found = [*(facts(r, line.get(r.id)) for r in session), *(f for f in stored if f.id not in known)]
        return ProcessSnapshot(tuple(describe(f, at) for f in found), problem)
