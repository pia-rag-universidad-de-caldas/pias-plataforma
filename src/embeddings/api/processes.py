"""What embeddings has going on (as feature 039): the runs and experiments of this session and, read from the graph,
those of the past."""

from collections.abc import Callable, Sequence
from datetime import datetime

from common.processes import History, ProcessFacts, ProcessSnapshot, ProcessState, describe
from embeddings.models import DocumentError, EmbeddingRun, RunStatus, UpstreamDown

from .registry import RunRegistry
from .work_queue import WorkQueue

MODULE = "embeddings"
_STATE = {
    RunStatus.QUEUED: ProcessState.QUEUED,
    RunStatus.RUNNING: ProcessState.RUNNING,
    RunStatus.FINISHED: ProcessState.FINISHED,
    RunStatus.FAILED: ProcessState.FAILED,
    RunStatus.INTERRUPTED: ProcessState.INTERRUPTED,
    RunStatus.CANCELLED: ProcessState.CANCELLED,
}


def facts(run: EmbeddingRun, position: int | None) -> ProcessFacts:
    progress = run.progress
    name = run.name or ("embeddings experiment" if run.chunking_experiment else "embeddings run")
    return ProcessFacts(
        run.id,
        MODULE,
        run.kind.value,
        name,
        _STATE[run.status],
        run.requested,
        started=run.started,
        finished=run.finished,
        position=position,
        strategies=(f"{run.config.model} max_tokens={run.config.max_tokens}",),
        done=progress.done,
        total=progress.total,
        counters={
            "embedded": progress.embedded,
            "chunks": progress.chunks,
            "unchanged": progress.unchanged,
            "skipped": progress.skipped,
            "missing": progress.missing,
            "errors": progress.errors,
        },
        error=run.error,
    )


class EmbeddingProcesses:
    def __init__(self, queue: WorkQueue, runs: RunRegistry, stored: Callable[[], Sequence[EmbeddingRun]]) -> None:
        self._queue, self._runs = queue, runs
        self._history = History(lambda: [facts(r, None) for r in stored()], (UpstreamDown, DocumentError))
        runs.on_done = self._history.expire

    def snapshot(self, at: datetime) -> ProcessSnapshot:
        line = {id: place for place, id in enumerate(self._queue.waiting(), start=1)}
        session = self._runs.all()
        known = {r.id for r in session}
        stored, problem = self._history.current()
        found = [*(facts(r, line.get(r.id)) for r in session), *(f for f in stored if f.id not in known)]
        return ProcessSnapshot(tuple(describe(f, at) for f in found), problem)
