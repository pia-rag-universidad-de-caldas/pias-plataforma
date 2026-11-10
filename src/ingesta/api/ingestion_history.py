"""The ingestions of past server sessions (feature 039): each one is saved when it starts and when it ends, in the
memory, as the JSON GET /runs answers. One still `en_curso` that this server isn't running was interrupted."""

import json
import logging
from dataclasses import replace

from fastapi.encoders import jsonable_encoder
from pydantic import TypeAdapter

from ingesta.adapters import SQLORMAdapter, create_adapter
from ingesta.models import IngestionRecord, MemoryStoreError
from ingesta.repository import DbIngestionRepository
from ingesta.tables import TABLES

from .schemas import IngestionRun, IngestionState

LOG = logging.getLogger(__name__)
_RUN = TypeAdapter(IngestionRun)


def save_run(memory: str, run: IngestionRun) -> None:
    """The memory is created if it doesn't exist. If it can't be written the run goes on: only its history is lost."""
    record = IngestionRecord(run.id, run.estado.value, run.inicio, json.dumps(jsonable_encoder(run)), run.fin)
    try:
        data = create_adapter(memory, TABLES)
        try:
            DbIngestionRepository(data).save(record)
        finally:
            data.close()
    except MemoryStoreError as error:
        LOG.warning("the ingestion %s wasn't saved: %s", run.id, error)


def _run(record: IngestionRecord) -> IngestionRun:
    """A stored one: `en_curso` here means it was interrupted, since the registry has those that do run."""
    run = _RUN.validate_python(json.loads(record.detalle))
    return replace(run, estado=IngestionState.INTERRUPTED) if run.estado is IngestionState.RUNNING else run


def stored_runs(memory: str) -> list[IngestionRun]:
    """Newest first; none if there is no memory yet. MemoryStoreError if it can't be read."""
    try:
        data = SQLORMAdapter.from_existing(memory, TABLES)
    except MemoryStoreError:
        return []
    try:
        return [_run(record) for record in DbIngestionRepository(data).all()]
    finally:
        data.close()


def stored_run(memory: str, id: str) -> IngestionRun | None:
    try:
        data = SQLORMAdapter.from_existing(memory, TABLES)
    except MemoryStoreError:
        return None
    try:
        record = DbIngestionRepository(data).find(id)
    finally:
        data.close()
    return _run(record) if record is not None else None
