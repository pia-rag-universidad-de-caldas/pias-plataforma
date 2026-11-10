"""What llm has going on (as feature 039): the pulls of this session. Nothing is read from data: a pull is only kept
in memory, and Ollama keeps the model."""

from datetime import datetime

from common.processes import ProcessFacts, ProcessSnapshot, ProcessState, describe
from llm.models import ModelPull, PullStatus

from .registry import PullRegistry
from .work_queue import WorkQueue

MODULE = "llm"
KIND = "pull"
_STATE = {
    PullStatus.QUEUED: ProcessState.QUEUED,
    PullStatus.RUNNING: ProcessState.RUNNING,
    PullStatus.FINISHED: ProcessState.FINISHED,
    PullStatus.FAILED: ProcessState.FAILED,
}


def facts(pull: ModelPull, position: int | None) -> ProcessFacts:
    return ProcessFacts(
        pull.id,
        MODULE,
        KIND,
        f"ollama pull {pull.model}",
        _STATE[pull.status],
        pull.requested,
        started=pull.started,
        finished=pull.finished,
        position=position,
        strategies=(pull.model,),
        done=pull.completed,  # bytes of the layer being downloaded: the large one is most of the model
        total=pull.total,
        detail=pull.step,
        error=pull.error,
    )


class LlmProcesses:
    def __init__(self, queue: WorkQueue, pulls: PullRegistry) -> None:
        self._queue, self._pulls = queue, pulls

    def snapshot(self, at: datetime) -> ProcessSnapshot:
        line = {id: place for place, id in enumerate(self._queue.waiting(), start=1)}
        return ProcessSnapshot(tuple(describe(facts(p, line.get(p.id)), at) for p in self._pulls.all()))
