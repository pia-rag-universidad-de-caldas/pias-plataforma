"""What chunking has going on (feature 039): the line, the runs and the experiments; those that ended are read from
the graph."""

from collections.abc import Callable, Sequence
from datetime import datetime

from chunking.models import ChunkingRun, DocumentError, ExperimentRecord, ExperimentStatus, RunStatus, SinkError
from common.processes import History, ProcessFacts, ProcessSnapshot, ProcessState, describe

from .experiments import ExperimentRegistry, LiveExperiment
from .runs import RunRegistry
from .work_queue import WorkQueue

MODULE = "chunking"
EXPERIMENT = "experiment"
RUN = "run"
_ENDED_EXPERIMENT = {
    ExperimentStatus.FINISHED: ProcessState.FINISHED,
    ExperimentStatus.PARTIAL: ProcessState.FINISHED,  # with its errors in the counters
    ExperimentStatus.FAILED: ProcessState.FAILED,
    ExperimentStatus.INTERRUPTED: ProcessState.INTERRUPTED,
    ExperimentStatus.QUEUED: ProcessState.INTERRUPTED,  # stored so, but this server doesn't have it
    ExperimentStatus.RUNNING: ProcessState.INTERRUPTED,  # same
}
_STATE = {
    RunStatus.QUEUED: ProcessState.QUEUED,
    RunStatus.RUNNING: ProcessState.RUNNING,
    RunStatus.FINISHED: ProcessState.FINISHED,
    RunStatus.PARTIAL: ProcessState.FINISHED,
    RunStatus.FAILED: ProcessState.FAILED,
    RunStatus.INTERRUPTED: ProcessState.INTERRUPTED,
}


def _how(run: ChunkingRun) -> str:
    p = run.parameters
    return f"docling {p.chunker.value}" + (f" max_tokens={p.max_tokens}" if p.max_tokens else "")


def _stored(record: ExperimentRecord) -> ProcessFacts:
    return ProcessFacts(
        record.id,
        MODULE,
        EXPERIMENT,
        record.name,
        _ENDED_EXPERIMENT[record.status],
        record.created,
        started=record.started or record.created,
        finished=record.finished,
        error=record.error,
    )


def _live(experiment: LiveExperiment, position: int | None) -> ProcessFacts:
    progress = experiment.progress
    return ProcessFacts(
        experiment.id,
        MODULE,
        EXPERIMENT,
        experiment.name,
        ProcessState.RUNNING if experiment.started else ProcessState.QUEUED,
        experiment.requested,
        started=experiment.started,
        position=position,
        strategies=experiment.strategies,
        done=progress.done,
        total=progress.files,
        counters={"chunks": progress.chunks, "errors": progress.errors},
    )


def _run(run: ChunkingRun, position: int | None) -> ProcessFacts:
    progress = run.progress
    return ProcessFacts(
        run.id,
        MODULE,
        RUN,
        f"run (resumed {run.resumed})" if run.resumed else "run",
        _STATE[run.status],
        run.requested,
        started=run.started,
        finished=run.finished,
        position=position,
        strategies=(_how(run),),
        done=progress.chunked + progress.skipped + progress.unparsed + progress.errors,
        total=run.documents,
        counters={"chunks": progress.chunks, "skipped": progress.skipped, "errors": progress.errors},
        error=run.error,
    )


class ChunkingProcesses:
    def __init__(
        self,
        queue: WorkQueue,
        experiments: ExperimentRegistry,
        runs: RunRegistry,
        records: Callable[[], Sequence[ExperimentRecord]],
        stored_runs: Callable[[], Sequence[ChunkingRun]],
    ) -> None:
        self._queue, self._experiments, self._runs = queue, experiments, runs
        self._history = History(
            lambda: [*(_stored(r) for r in records()), *(_run(r, None) for r in stored_runs())],
            (SinkError, DocumentError),
        )
        experiments.on_done = self._history.expire
        runs.on_done = self._history.expire

    def snapshot(self, at: datetime) -> ProcessSnapshot:
        line = {id: place for place, id in enumerate(self._queue.waiting(), start=1)}
        live = self._experiments.live()
        session = self._runs.all()
        known = {e.id for e in live} | {r.id for r in session}
        stored, problem = self._history.current()
        facts = [
            *(_live(e, line.get(e.id)) for e in live),
            *(_run(r, line.get(r.id)) for r in session),
            *(f for f in stored if f.id not in known),
        ]
        return ProcessSnapshot(tuple(describe(f, at) for f in facts), problem)
