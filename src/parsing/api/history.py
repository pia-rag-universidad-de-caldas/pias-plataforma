"""The runs of past server sessions (as feature 041): each one is stored in data (CORRIDA_PARSEO) when it is asked for,
when its turn comes and when it ends, as the JSON GET /runs answers. One still queued or running that this server
isn't running was interrupted."""

import json
import logging
from dataclasses import replace

from fastapi.encoders import jsonable_encoder
from pydantic import TypeAdapter, ValidationError

from parsing.models import DocumentError, ParsingRun, RunStatus, RunStore, SinkError

LOG = logging.getLogger(__name__)
_RUN = TypeAdapter(ParsingRun)
_ALIVE = frozenset({RunStatus.QUEUED, RunStatus.RUNNING})


def save(store: RunStore, run: ParsingRun) -> None:
    """If data doesn't answer the run goes on: only its record is behind."""
    try:
        store.save(run.id, run.status.value, run.requested, json.dumps(jsonable_encoder(run), ensure_ascii=False))
    except (SinkError, DocumentError) as error:
        LOG.warning("the parsing run %s wasn't stored: %s", run.id, error)


def _read(detail: str) -> ParsingRun | None:
    try:
        run = _RUN.validate_python(json.loads(detail))
    except (ValueError, ValidationError):
        return None
    return replace(run, status=RunStatus.INTERRUPTED) if run.status in _ALIVE else run


def stored_runs(store: RunStore) -> list[ParsingRun]:
    """Newest first. SinkError if data doesn't answer."""
    found = [run for run in (_read(detail) for detail in store.details()) if run is not None]
    return sorted(found, key=lambda run: run.requested, reverse=True)


def stored_run(store: RunStore, id: str) -> ParsingRun | None:
    detail = store.detail(id)
    return _read(detail) if detail is not None else None
