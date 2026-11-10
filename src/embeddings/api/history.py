"""The runs and experiments of past server sessions (as feature 041): each one is stored in data when it is asked for,
when its turn comes and when it ends, as the JSON GET answers. One still queued or running that this server isn't
running was interrupted."""

import json
import logging
from dataclasses import replace

from fastapi.encoders import jsonable_encoder
from pydantic import TypeAdapter, ValidationError

from embeddings.models import ALIVE, DocumentError, EmbeddingRun, RunKind, RunStatus, RunStore, UpstreamDown

LOG = logging.getLogger(__name__)
_RUN = TypeAdapter(EmbeddingRun)


def detail(run: EmbeddingRun) -> str:
    return json.dumps(jsonable_encoder(run), ensure_ascii=False)


def save(store: RunStore, run: EmbeddingRun) -> None:
    """If data doesn't answer the run goes on: only its record is behind."""
    try:
        store.save(run.kind, run.id, run.status.value, run.requested, detail(run))
    except (UpstreamDown, DocumentError) as error:
        LOG.warning("the embeddings %s %s wasn't stored: %s", run.kind.value, run.id, error)


def _read(text: str) -> EmbeddingRun | None:
    try:
        run = _RUN.validate_python(json.loads(text))
    except (ValueError, ValidationError):
        return None
    return replace(run, status=RunStatus.INTERRUPTED) if run.status in ALIVE else run


def stored_runs(store: RunStore, kind: RunKind) -> list[EmbeddingRun]:
    """Newest first. UpstreamDown if data doesn't answer."""
    found = [run for run in (_read(text) for text in store.details(kind)) if run is not None]
    return sorted(found, key=lambda run: run.requested, reverse=True)


def stored_run(store: RunStore, kind: RunKind, id: str) -> EmbeddingRun | None:
    text = store.detail(kind, id)
    return _read(text) if text is not None else None
