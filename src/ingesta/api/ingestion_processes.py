"""The ingestions as processes of the board (features 039 and 041)."""

from datetime import datetime

from common.processes import History, ProcessFacts, ProcessSnapshot, ProcessState, describe
from ingesta.models import (
    MemoryStoreError,
)

from .ingestion_history import stored_runs
from .ingestion_registry import IngestionRegistry
from .schemas import IngestionRun, IngestionState

_STATE = {
    IngestionState.RUNNING: ProcessState.RUNNING,
    IngestionState.FINISHED: ProcessState.FINISHED,
    IngestionState.FAILED: ProcessState.FAILED,
    IngestionState.INTERRUPTED: ProcessState.INTERRUPTED,
}


def _facts(run: IngestionRun) -> ProcessFacts:
    return ProcessFacts(
        run.id,
        "ingesta",
        "ingestion",
        f"ingestion from {run.revision.tipo.value}",
        _STATE[run.estado],
        run.inicio,
        started=run.inicio,
        finished=run.fin,
        done=run.progreso.copiados,
        total=run.progreso.total,
        counters={"errors": len(run.errores)},
        error=run.error,
    )


class IngestionProcesses:
    """The ingestions as processes (feature 039): those of this session, and the past ones from the memory (feature
    041). There is no line: another one is a 409."""

    def __init__(self, registry: IngestionRegistry, memory: str) -> None:
        self._registry = registry
        self._history = History(lambda: [_facts(run) for run in stored_runs(memory)], (MemoryStoreError,))
        registry.on_done = self._history.expire

    def snapshot(self, at: datetime) -> ProcessSnapshot:
        live = [_facts(run) for run in self._registry.all()]
        known = {f.id for f in live}
        stored, problem = self._history.current()
        facts = [*live, *(f for f in stored if f.id not in known)]
        return ProcessSnapshot(tuple(describe(f, at) for f in facts), problem)
