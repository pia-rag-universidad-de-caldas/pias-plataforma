"""The worker of an ingestion started from the API (feature 030): it runs in its own thread, with its own memory
connection (the SQLConverter isn't shared across threads)."""

import logging
from contextlib import ExitStack

from common.clock import now
from common.logs import brief
from ingesta.adapters import LocalFileAdapter, create_adapter, open_source, raw_store
from ingesta.domain import Ingestion, IngestionObserver
from ingesta.models import (
    FileError,
    FileFailure,
    IngestionOutcome,
    MemoryStoreError,
    OrganizationPlan,
    SourceUnavailable,
)
from ingesta.repository import DbCategoryRepository, DbFileRepository, DbRunRepository
from ingesta.tables import TABLES

from .dependencies import ApiSettings
from .ingestion_history import save_run
from .ingestion_registry import IngestionRegistry
from .schemas import IngestionSummary

LOG = logging.getLogger(__name__)


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
        en_data=outcome.raw,
    )


class _RegistryObserver(IngestionObserver):
    """A run's copies and failures, into its entry of the registry (GET /runs/{id})."""

    def __init__(self, registry: IngestionRegistry, id: str) -> None:
        self._registry, self._id = registry, id

    def copied(self, done: int, total: int) -> None:
        self._registry.progress(self._id, done)

    def failed(self, failure: FileFailure) -> None:
        self._registry.failure(self._id, failure)
        LOG.warning("ingestion %s: file %s failed: %s", self._id, brief(failure.origin), brief(failure.error))


def work(registry: IngestionRegistry, id: str, settings: ApiSettings, plan: OrganizationPlan) -> None:
    """Runs one ingestion (in its thread): copies the new files of the source, never moving them, and places the
    corpus. A failure of the whole run (memory down, source gone...) leaves it as fallida with the reason."""
    run = registry.get(id)
    assert run is not None
    LOG.info("ingestion %s started: %d new files", id, run.progreso.total)

    def finish(result: IngestionSummary | None, error: str | None) -> None:
        registry.finish(id, result, error)
        ended = registry.get(id)
        if ended is not None:
            save_run(settings.memory, ended)
        registry.on_done()
        if result is not None:
            LOG.info("ingestion %s finished: copied=%d errors=%d", id, result.copiados, result.errores)
            raw = result.en_data
            if raw is not None and raw.aviso:
                LOG.warning("ingestion %s: %s", id, brief(raw.aviso))
            elif raw is not None:
                LOG.info(
                    "ingestion %s: data published=%d retired=%d failed=%d", id, raw.subidos, raw.retirados, raw.fallidos
                )
        else:
            LOG.error("ingestion %s stopped: %s", id, brief(error or "unknown"))

    try:
        source = open_source(run.revision.tipo, run.revision.ubicacion)
        ingest = LocalFileAdapter(settings.ingest)
        ingest.make_dir()
        save_run(settings.memory, run)
        data = create_adapter(settings.memory, TABLES)  # the memory is created if it doesn't exist
        try:
            with ExitStack() as stack:
                published = None
                if settings.self_url:  # feature 042: the chunkable files, published in data at the end
                    store = stack.enter_context(raw_store(settings.self_url, settings.data_path))
                    published = (store, settings.raw_limit, now())
                outcome = Ingestion.run(
                    plan,
                    source,
                    ingest,
                    DbFileRepository(data),
                    DbRunRepository(data),
                    DbCategoryRepository(data),
                    _RegistryObserver(registry, id),
                    progress_every=1,
                    raw=published,
                )
        finally:
            data.close()
    except (MemoryStoreError, FileError, SourceUnavailable) as e:
        finish(None, str(e))
        return
    except Exception as e:  # any other bug: the run must not stay en_curso forever
        finish(None, f"unexpected error: {type(e).__name__}: {e}")
        raise
    finish(summary(outcome), None)
