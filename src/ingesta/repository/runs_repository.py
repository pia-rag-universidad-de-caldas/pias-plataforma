"""Table of runs (implements models.RunRepository) on top of the agnostic adapter."""

from dataclasses import replace

from ingesta.models import Filter, MemoryStoreError, Operator, ORMAdapter, Run


class DbRunRepository:
    def __init__(self, data: ORMAdapter) -> None:
        self._data = data

    def start(self, start: str, action: str) -> int:
        run_id = self._data.create(Run(inicio=start, accion=action))
        if not isinstance(run_id, int):
            raise MemoryStoreError("the run could not be registered")
        return run_id

    def finish(self, run_id: int, end: str, new: int, skipped: int, errors: int) -> None:
        run = self._data.read(Run, run_id)
        if run is None:
            raise MemoryStoreError(f"the run {run_id} doesn't exist")
        self._data.update(replace(run, fin=end, nuevos=new, omitidos=skipped, errores=errors))

    def last_finished(self) -> Run | None:
        finished = self._data.search(Run, (Filter("fin", Operator.NOT_NULL),), order=("fin",))
        return finished[-1] if finished else None
