"""Chunking experiments (features 043 and 045): POST/GET /experiments, GET/DELETE /experiments/{id},
POST /experiments/{id}/apply and POST /experiments/{id}/resume. The record lives in the graph (experiment labels),
read and written through data over HTTP; the official chunks are never touched here. What an experiment chunked is
read in data (EXP_SECCION/EXP_CHUNK)."""

import json
from collections.abc import Iterable
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import JsonValue

from chunking.adapters.docling_chunkers import MISSING
from chunking.api.dependencies import Config, DocumentChunker, Experiments, Queue, Settings, Store
from chunking.api.experiments import ExperimentRegistry, LiveExperiment, experiment_request
from chunking.api.experiments.responses import DOWN, INVALID, NOT_FOUND
from chunking.api.experiments.schemas import (
    ExperimentStarted,
    ExperimentSummary,
    ExperimentView,
    NewExperiment,
)
from chunking.api.experiments.worker import launch
from chunking.api.routes.config import ConfigView, config_view
from chunking.api.work_queue import LINE_FULL
from chunking.domain import ExperimentGraph, ExperimentRunner, Parameters
from chunking.models import (
    RESUMABLE_EXPERIMENTS,
    ActiveConfig,
    ChunkingParameters,
    ConfigOrigin,
    ExperimentProgress,
    ExperimentRecord,
    ExperimentRequest,
    ExperimentStatus,
    ExperimentStore,
)
from common.api import Error
from common.clock import now

router = APIRouter(prefix="/experiments", tags=["experiments"])
UNPARSED_ONLY = "none of the documents is parsed: parse them first (POST /parsing/runs)"


def _loads(text: str | None) -> JsonValue:
    if text is None:
        return None
    try:
        loaded: JsonValue = json.loads(text)
    except ValueError:
        return text
    return loaded


def _record(store: ExperimentStore, id: str) -> ExperimentRecord:
    record = store.experiment(id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"there is no experiment with id {id!r}")
    return record


def _how(parameters: ChunkingParameters) -> str:
    sized = f" max_tokens={parameters.max_tokens}" if parameters.max_tokens else ""
    return f"docling {parameters.chunker.value}{sized}"


def _asked(record: ExperimentRecord, parameters: ChunkingParameters) -> ExperimentRequest:
    """The request of a stored experiment, back (to resume it)."""
    asked = _loads(record.documents_json)
    sha256s = asked.get("sha256s") if isinstance(asked, dict) else None
    origin = asked.get("from_experiment") if isinstance(asked, dict) else None
    return ExperimentRequest(
        record.name,
        record.description,
        parameters,
        [str(s) for s in sha256s] if isinstance(sha256s, list) else [],
        str(origin) if isinstance(origin, str) else None,
    )


def _summaries(records: Iterable[ExperimentRecord], experiments: ExperimentRegistry) -> list[ExperimentSummary]:
    return [
        ExperimentSummary(r.id, r.name, r.description, experiments.status(r), r.created, r.finished, r.progress)
        for r in records
    ]


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    responses=NOT_FOUND
    | DOWN
    | INVALID
    | {
        200: {"model": ExperimentStarted, "description": "simulate: what would enter, nothing stored"},
        409: {"model": Error, "description": "the line is full, or none of the documents is parsed"},
        503: {"model": Error, "description": "docling-core is not installed (uv sync --extra chunk), or data is down"},
    },
)
def start_experiment(
    settings: Settings,
    store: Store,
    experiments: Experiments,
    queue: Queue,
    chunker: DocumentChunker,
    new: NewExperiment,
    response: Response,
) -> ExperimentStarted:
    """Chunks the given parsed documents (`sha256s`, or those of `from_experiment`) with a configuration, apart from the
    official chunks: (:EXPERIMENTO)-[:EXP_USA]->(:JSON), (:EXPERIMENTO)-[:EXP_GENERA]->(:EXP_SECCION)-[:EXP_TIENE_CHUNK]
    ->(:EXP_CHUNK). Puts it in line and answers at once (202, `queued` if something else runs). A sha256 without a parse
    is `sin_parseo` and doesn't enter. With `simulate`, only which would enter (200, nothing stored)."""
    if queue.full and not new.simulate:
        raise HTTPException(status.HTTP_409_CONFLICT, LINE_FULL)
    request = experiment_request(new, chunker.version() or "")
    if request.from_experiment:
        _record(store, request.from_experiment)
    resolution = ExperimentRunner.resolve(store, request)
    if not resolution.sha256s:
        raise HTTPException(status.HTTP_409_CONFLICT, UNPARSED_ONLY)
    answer = ExperimentStarted(
        id=None,
        status="simulated",
        documents=resolution.sha256s,
        unparsed=resolution.unparsed,
        chunking=request.parameters.configurable(),
    )
    if new.simulate:
        response.status_code = status.HTTP_200_OK
        return answer
    if not chunker.available():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, MISSING)
    id, created = uuid4().hex[:12], now()
    store.save(ExperimentGraph.experiment(id, request, len(resolution.sha256s), created))
    busy = queue.busy
    parameters = request.parameters
    experiments.add(
        LiveExperiment(
            id, request.name, (_how(parameters),), created, progress=ExperimentProgress(files=len(resolution.sha256s))
        )
    )
    launch(queue, experiments, id, settings.session, chunker, request, resolution)
    return ExperimentStarted(
        id=id,
        status="queued" if busy else "running",
        documents=answer.documents,
        unparsed=answer.unparsed,
        chunking=answer.chunking,
    )


@router.get("", responses=DOWN)
def list_experiments(store: Store, experiments: Experiments) -> list[ExperimentSummary]:
    """Every experiment in the graph (not only this session's), newest first."""
    return _summaries(store.experiments(), experiments)


@router.get("/{id}", responses=NOT_FOUND | DOWN)
def read_experiment(store: Store, experiments: Experiments, id: str) -> ExperimentView:
    """The request, its progress and its results; `chunked` says which sha256s were chunked."""
    r = _record(store, id)
    chunked = [d.sha256 for d in r.results.by_document] if r.results else []
    return ExperimentView(
        r.id,
        r.name,
        r.description,
        experiments.status(r),
        r.created,
        r.started,
        r.finished,
        r.progress,
        _loads(r.documents_json),
        _loads(r.chunking_json),
        chunked,
        _loads(r.results_json),
        r.error,
    )


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=NOT_FOUND | DOWN | {409: {"model": Error, "description": "it is running"}},
)
def delete_experiment(store: Store, experiments: Experiments, id: str) -> None:
    """Deletes the experiment, its sections and chunks; the JSON stay. One in line leaves the line."""
    if experiments.active == id:
        raise HTTPException(status.HTTP_409_CONFLICT, "the experiment is running")
    experiments.cancel(id)
    if not store.delete(id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"there is no experiment with id {id!r}")


@router.post(
    "/{id}/apply",
    responses=NOT_FOUND | DOWN | {409: {"model": Error, "description": "the experiment didn't finish"}},
)
def apply_experiment(
    store: Store, experiments: Experiments, config: Config, chunker: DocumentChunker, id: str
) -> ConfigView:
    """Copies the configuration of a finished experiment to the active one. Nothing is chunked: that is
    POST /runs."""
    record = _record(store, id)
    if experiments.active == id or record.status != ExperimentStatus.FINISHED:
        raise HTTPException(status.HTTP_409_CONFLICT, f"the experiment is {experiments.status(record)}")
    parameters = record.parameters
    if parameters is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "the configuration of that experiment can't be read")
    active = ActiveConfig(Parameters.requested(parameters), ConfigOrigin.EXPERIMENT, id, now())
    config.put(active)
    return config_view(active, chunker.version() or "")


@router.post(
    "/{id}/resume",
    status_code=status.HTTP_202_ACCEPTED,
    responses=NOT_FOUND
    | DOWN
    | {
        409: {
            "model": Error,
            "description": "it isn't partial, failed or interrupted, nothing is left to chunk, or the line is full",
        },
        503: {"model": Error, "description": "docling-core is not installed (uv sync --extra chunk), or data is down"},
    },
)
def resume_experiment(
    settings: Settings, store: Store, experiments: Experiments, queue: Queue, chunker: DocumentChunker, id: str
) -> ExperimentStarted:
    """Chunks, with its own configuration, the documents of the experiment it didn't get to chunk (those that failed
    or weren't reached); the chunked ones stay. Only of a `partial`, `failed` or `interrupted` experiment. The same id:
    it goes back in line and its results count every document."""
    record = _record(store, id)
    current = experiments.status(record)
    if experiments.has(id) or current not in RESUMABLE_EXPERIMENTS:
        raise HTTPException(status.HTTP_409_CONFLICT, f"the experiment is {current.value}: there is nothing to resume")
    parameters = record.parameters
    if parameters is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "the configuration of that experiment can't be read")
    request = _asked(record, parameters)
    resolution, kept = ExperimentRunner.pending(store, request, store.uses(id))
    if not resolution.sha256s:
        raise HTTPException(status.HTTP_409_CONFLICT, "nothing is left to chunk: " + UNPARSED_ONLY)
    if queue.full:
        raise HTTPException(status.HTTP_409_CONFLICT, LINE_FULL)
    if not chunker.available():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, MISSING)
    files = len(resolution.sha256s) + len(kept)
    store.save(ExperimentGraph.resumed(id, files))
    busy = queue.busy
    experiments.add(
        LiveExperiment(id, record.name, (_how(parameters),), now(), progress=ExperimentProgress(files=files))
    )
    launch(queue, experiments, id, settings.session, chunker, request, resolution, kept)
    return ExperimentStarted(
        id=id,
        status="queued" if busy else "running",
        documents=resolution.sha256s,
        unparsed=resolution.unparsed,
        chunking=parameters.configurable(),
    )
