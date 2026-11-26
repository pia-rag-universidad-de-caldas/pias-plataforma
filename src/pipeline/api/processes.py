"""The pipeline's runs as processes (feature 039), read from the graph: they outlive the server."""

from datetime import datetime

from common.processes import History, ProcessFacts, ProcessSnapshot, ProcessState, describe
from pipeline.domain import Engine
from pipeline.models import PipelineError, PipelineRun, RunStatus, RunStore

from .executor import Executor

_STATE = {
    RunStatus.QUEUED: ProcessState.QUEUED,
    RunStatus.RUNNING: ProcessState.RUNNING,
    RunStatus.WAITING: ProcessState.WAITING,
    RunStatus.DONE: ProcessState.FINISHED,
    RunStatus.FAILED: ProcessState.FAILED,
    RunStatus.CANCELLED: ProcessState.CANCELLED,
    RunStatus.INTERRUPTED: ProcessState.INTERRUPTED,
}


def _detail(run: PipelineRun) -> str | None:
    if run.waiting is not None:
        return f"stage {run.waiting.step}: waiting for {run.waiting.actor}"
    stage = Engine.stage_id(run)
    return f"stage {stage}" if stage else None


class PipelineProcesses:
    def __init__(self, store: RunStore, executor: Executor) -> None:
        self._executor = executor
        self._history = History(lambda: [self._facts(run) for run in store.runs()], (PipelineError,))

    def _facts(self, run: PipelineRun) -> ProcessFacts:
        return ProcessFacts(
            run.id,
            "pipeline",
            "run",
            run.name or run.template.name,
            _STATE[self._executor.status(run)],
            run.created,
            started=run.created,
            finished=run.finished,
            done=run.cursor.stage,
            total=len(run.template.stages),
            detail=_detail(run),
            error=run.error,
        )

    def snapshot(self, at: datetime) -> ProcessSnapshot:
        facts, problem = self._history.current()
        return ProcessSnapshot(tuple(describe(f, at) for f in facts), problem)
