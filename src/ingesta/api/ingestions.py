"""The ingestions started from the API (feature 030): an in-memory registry (one at a time) and the worker that runs
each one in its own thread, with its own memory connection (the SQLConverter isn't shared across threads)."""

import threading
import uuid
from dataclasses import replace
from datetime import datetime

from ingesta.adapters import LocalFileAdapter, create_adapter, open_source
from ingesta.domain import Ingestion
from ingesta.models import (
    FileError,
    FileFailure,
    IngestionOutcome,
    MemoryStoreError,
    OrganizationPlan,
    SourceCheck,
    SourceUnavailable,
)
from ingesta.repository import DbCategoryRepository, DbFileRepository, DbRunRepository
from ingesta.tables import TABLES

from .dependencies import ApiSettings
from .schemas import FileFailureItem, IngestionProgress, IngestionRun, IngestionState, IngestionSummary

MAX_FAILURES = 200  # file failures kept in a run (all of them count in its summary)


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def summary(outcome: IngestionOutcome) -> IngestionSummary:
    placement, changes = outcome.placement, outcome.placement.changes
    return IngestionSummary(
        copiados=outcome.run.processed,
        errores=len(outcome.run.failures),
        hashes_rellenados=outcome.hashes_filled,
        metadata_rellenada=outcome.metadata_filled,
        reubicados=len(placement.relocated),
        categorias_agregadas=changes.added if changes else 0,
        categorias_quitadas=changes.removed if changes else 0,
        principal_cambiada=changes.main_changed if changes else 0,
        carpetas=placement.main,
        con_cada_categoria=placement.every,
        duplicados=outcome.duplicates,
        duplicados_nuevos=len(outcome.new_duplicates),
    )


class IngestionRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, IngestionRun] = {}  # in start order

    def start(self, check: SourceCheck, total: int) -> IngestionRun | None:
        """Registers a new run unless another one is still running (None then)."""
        with self._lock:
            if any(r.estado is IngestionState.RUNNING for r in self._runs.values()):
                return None
            run = IngestionRun(
                uuid.uuid4().hex[:12], IngestionState.RUNNING, now(), None, check, IngestionProgress(0, total)
            )
            self._runs[run.id] = run
            return run

    def get(self, id: str) -> IngestionRun | None:
        with self._lock:
            return self._runs.get(id)

    def all(self) -> list[IngestionRun]:
        """Newest first."""
        with self._lock:
            return list(reversed(self._runs.values()))

    def progress(self, id: str, done: int) -> None:
        with self._lock:
            run = self._runs[id]
            self._runs[id] = replace(run, progreso=replace(run.progreso, copiados=done))

    def failure(self, id: str, failure: FileFailure) -> None:
        with self._lock:
            run = self._runs[id]
            if len(run.errores) < MAX_FAILURES:
                item = FileFailureItem(failure.origin, failure.error, failure.target)
                self._runs[id] = replace(run, errores=[*run.errores, item])

    def finish(self, id: str, result: IngestionSummary | None, error: str | None) -> None:
        with self._lock:
            run = self._runs[id]
            state = IngestionState.FAILED if error else IngestionState.FINISHED
            progress = replace(run.progreso, copiados=result.copiados) if result else run.progreso
            self._runs[id] = replace(run, estado=state, fin=now(), progreso=progress, resultado=result, error=error)


def work(registry: IngestionRegistry, id: str, settings: ApiSettings, plan: OrganizationPlan) -> None:
    """Runs one ingestion (in its thread): copies the new files of the source, never moving them, and places the
    corpus. A failure of the whole run (memory down, source gone...) leaves it as fallida with the reason."""
    run = registry.get(id)
    assert run is not None
    try:
        source = open_source(run.revision.tipo, run.revision.ubicacion)
        ingest = LocalFileAdapter(settings.ingest)
        ingest.make_dir()
        data = create_adapter(settings.memory, TABLES)  # the memory is created if it doesn't exist
        try:
            outcome = Ingestion.run(
                plan,
                source,
                ingest,
                DbFileRepository(data),
                DbRunRepository(data),
                DbCategoryRepository(data),
                on_progress=lambda done, _total: registry.progress(id, done),
                on_failure=lambda failure: registry.failure(id, failure),
                progress_every=1,
            )
        finally:
            data.close()
    except (MemoryStoreError, FileError, SourceUnavailable) as e:
        registry.finish(id, None, str(e))
        return
    except Exception as e:  # any other bug: the run must not stay en_curso forever
        registry.finish(id, None, f"unexpected error: {type(e).__name__}: {e}")
        raise
    registry.finish(id, summary(outcome), None)
