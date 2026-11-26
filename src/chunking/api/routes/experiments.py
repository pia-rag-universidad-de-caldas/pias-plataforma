"""Chunking experiments (features 043 and 045): POST/GET /experiments, GET/DELETE /experiments/{id},
POST /experiments/{id}/apply and POST /experiments/{id}/resume. The record lives in the graph (experiment labels),
read and written through data over HTTP; the official chunks are never touched here. What an experiment chunked is
read in data (EXP_DOCUMENTO/EXP_SECCION/EXP_CHUNK)."""

import json
import logging
from collections.abc import Iterable
from dataclasses import replace
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import JsonValue

from chunking.adapters.docling_chunkers import MISSING
from chunking.api.dependencies import Config, DocumentChunker, Experiments, Queue, Settings, Store
from chunking.api.experiments import ExperimentRegistry, LiveExperiment, experiment_request
from chunking.api.experiments.responses import DOWN, INVALID, NOT_FOUND
from chunking.api.experiments.schemas import (
    DocumentsAdded,
    ExperimentStarted,
    ExperimentSummary,
    ExperimentView,
    NewDocuments,
    NewExperiment,
)
from chunking.api.experiments.worker import launch
from chunking.api.routes.config import ConfigView, config_view
from chunking.api.work_queue import LINE_FULL
from chunking.domain import ExperimentGraph, ExperimentRunner, Parameters, Resolution
from chunking.domain.experiments.graph import ADDED, CREATED
from chunking.models import (
    RESUMABLE_EXPERIMENTS,
    ActiveConfig,
    ChunkingParameters,
    ConfigOrigin,
    DocumentUse,
    ExperimentProgress,
    ExperimentRecord,
    ExperimentRequest,
    ExperimentSelection,
    ExperimentStatus,
    ExperimentStore,
)
from common.api import Error
from common.clock import now

router = APIRouter(prefix="/experiments", tags=["experiments"])
LOG = logging.getLogger(__name__)
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
        record.all,
    )


def _selections(record: ExperimentRecord) -> list[ExperimentSelection]:
    """Those stored or, for an experiment of before feature 062, its creation with the documents it took."""
    return record.selections or [ExperimentSelection(record.created, CREATED, record.progress.files)]


def _summaries(records: Iterable[ExperimentRecord], experiments: ExperimentRegistry) -> list[ExperimentSummary]:
    return [
        ExperimentSummary(r.id, r.name, r.description, experiments.status(r), r.created, r.finished, r.progress, r.all)
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
    """Chunks the given parsed documents (`sha256s`, those of `from_experiment` or, with `all`, every parsed JSON data
    has when its turn comes: feature 059) with a configuration, apart from the official chunks:
    (:EXPERIMENTO)-[:EXP_TIENE_DOCUMENTO]->(:EXP_DOCUMENTO)-[:EXP_DE]->(:JSON),
    (:EXP_DOCUMENTO)-[:EXP_TIENE_SECCION]->(:EXP_SECCION)-[:EXP_TIENE_CHUNK]->(:EXP_CHUNK). Puts it in line and
    answers at once (202, `queued` if something else runs). A sha256 without a parse is `sin_parseo` and doesn't
    enter. With `simulate`, only which would enter (200, nothing stored; with `all`, only how many: `total`)."""
    if queue.full and not new.simulate:
        raise HTTPException(status.HTTP_409_CONFLICT, LINE_FULL)
    request = experiment_request(new, chunker.version() or "")
    if request.from_experiment:
        _record(store, request.from_experiment)
    resolution = None if request.all else ExperimentRunner.resolve(store, request)
    total = store.parsed_count() if resolution is None else len(resolution.sha256s)
    if not total:
        raise HTTPException(status.HTTP_409_CONFLICT, UNPARSED_ONLY)
    answer = ExperimentStarted(
        id=None,
        status="simulated",
        documents=resolution.sha256s if resolution else [],
        unparsed=resolution.unparsed if resolution else [],
        chunking=request.parameters.configurable(),
        all=request.all,
        total=total,
    )
    if new.simulate:
        response.status_code = status.HTTP_200_OK
        return answer
    if not chunker.available():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, MISSING)
    id, created = uuid4().hex[:12], now()
    store.save(ExperimentGraph.experiment(id, request, total, created))
    busy = queue.busy
    parameters = request.parameters
    experiments.add(LiveExperiment(id, request.name, (_how(parameters),), created, progress=ExperimentProgress(total)))
    launch(queue, experiments, id, settings.session, chunker, request, resolution)
    return replace(answer, id=id, status="queued" if busy else "running")


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
        r.all,
        _selections(r),
    )


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=NOT_FOUND
    | DOWN
    | {
        409: {
            "model": Error,
            "description": "it is running, an embeddings experiment uses it, or (without force) a pipeline run "
            "links it",
        }
    },
)
def delete_experiment(
    store: Store,
    experiments: Experiments,
    id: str,
    force: Annotated[
        bool, Query(description="delete it even if a pipeline run links it (that run can't be saved again afterwards)")
    ] = False,
) -> None:
    """Deletes the experiment, its documents, sections, chunks and their vectors; the JSON stay. One in line leaves
    the line. 409 if an embeddings experiment uses its chunks (delete that one first: DELETE
    /embeddings/experiments/{id}) or, without `force`, if a pipeline run links it (PIPE_USA)."""
    if experiments.active == id:
        raise HTTPException(status.HTTP_409_CONFLICT, "the experiment is running")
    dependents = store.dependents(id)
    if dependents.embeddings:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"the embeddings experiments {', '.join(dependents.embeddings)} use its chunks: delete them first "
            "(DELETE /embeddings/experiments/{id})",
        )
    if dependents.pipeline and not force:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"the pipeline iterations {', '.join(dependents.pipeline)} link it: with force=true it is deleted anyway "
            "and those runs can't be saved again",
        )
    if dependents.pipeline:
        LOG.warning("experiment %s deleted with force: the pipeline iterations %s lose it", id, dependents.pipeline)
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
    it goes back in line and its results count every document. One of `all` takes every parsed JSON again when its
    turn comes, skipping those it chunked (it always goes in line: `documents` is empty)."""
    record = _record(store, id)
    current = experiments.status(record)
    if experiments.has(id) or current not in RESUMABLE_EXPERIMENTS:
        raise HTTPException(status.HTTP_409_CONFLICT, f"the experiment is {current.value}: there is nothing to resume")
    parameters = record.parameters
    if parameters is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "the configuration of that experiment can't be read")
    request = _asked(record, parameters)
    resolution: Resolution | None
    kept: list[DocumentUse]
    if request.all:  # what is left is only known reading it: it is taken when its turn comes (feature 059)
        resolution, kept, files = None, [], store.parsed_count()
    else:
        resolution, kept = ExperimentRunner.pending(store, request, store.uses(id))
        if not resolution.sha256s:
            raise HTTPException(status.HTTP_409_CONFLICT, "nothing is left to chunk: " + UNPARSED_ONLY)
        files = len(resolution.sha256s) + len(kept)
    if queue.full:
        raise HTTPException(status.HTTP_409_CONFLICT, LINE_FULL)
    if not chunker.available():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, MISSING)
    store.save(ExperimentGraph.resumed(id, files))
    busy = queue.busy
    experiments.add(
        LiveExperiment(id, record.name, (_how(parameters),), now(), progress=ExperimentProgress(files=files))
    )
    launch(queue, experiments, id, settings.session, chunker, request, resolution, kept)
    return ExperimentStarted(
        id=id,
        status="queued" if busy else "running",
        documents=resolution.sha256s if resolution else [],
        unparsed=resolution.unparsed if resolution else [],
        chunking=parameters.configurable(),
        all=request.all,
        total=files,
    )


ALIVE = (ExperimentStatus.QUEUED, ExperimentStatus.RUNNING)


@router.post(
    "/{id}/documents",
    status_code=status.HTTP_202_ACCEPTED,
    responses=NOT_FOUND
    | DOWN
    | {
        200: {"model": DocumentsAdded, "description": "simulate: what would enter, nothing stored"},
        409: {
            "model": Error,
            "description": "it is queued or running, none of the documents is new and parsed, or the line is full",
        },
        503: {"model": Error, "description": "docling-core is not installed (uv sync --extra chunk), or data is down"},
    },
)
def add_documents(
    settings: Settings,
    store: Store,
    experiments: Experiments,
    queue: Queue,
    chunker: DocumentChunker,
    id: str,
    new: NewDocuments,
    response: Response,
) -> DocumentsAdded:
    """Adds parsed documents to the experiment's frozen list (feature 062) and puts it in line: it chunks, with its
    own configuration (never another one), what was added and what it left pending or in error; what it chunked
    stays. Those it had are `already`; the new ones without a parse, `unparsed` (they don't enter). One of every
    parsed JSON (`all`, feature 059) becomes one of a list: the documents it got to plus the new ones. Each addition
    is one more of its `selections`. With `simulate`, only what would enter (200)."""
    record = _record(store, id)
    current = experiments.status(record)
    if experiments.has(id) or current in ALIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, f"the experiment is {current.value}: add documents once it ends")
    parameters = record.parameters
    if parameters is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "the configuration of that experiment can't be read")
    asked = _asked(record, parameters)
    listed = ExperimentRunner.listed(store, asked, id)
    addition = ExperimentRunner.addition(store, listed, new.sha256s)
    if not addition.added:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"nothing new to add: {len(addition.already)} already in it, {len(addition.unparsed)} without a parse",
        )
    request = replace(asked, sha256s=[*listed, *addition.added], all=False)
    answer = DocumentsAdded(id, "simulated", addition.added, addition.already, addition.unparsed, len(request.sha256s))
    if new.simulate:
        response.status_code = status.HTTP_200_OK
        return answer
    if queue.full:
        raise HTTPException(status.HTTP_409_CONFLICT, LINE_FULL)
    if not chunker.available():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, MISSING)
    resolution, kept = ExperimentRunner.pending(store, request, store.uses(id))
    files = len(resolution.sha256s) + len(kept)
    at = now()
    selections = [*_selections(record), ExperimentSelection(at, ADDED, len(addition.added))]
    store.save(ExperimentGraph.added(id, request, selections, files))
    busy = queue.busy
    experiments.add(LiveExperiment(id, record.name, (_how(parameters),), at, progress=ExperimentProgress(files=files)))
    launch(queue, experiments, id, settings.session, chunker, request, resolution, kept)
    LOG.info("experiment %s: %d documents added", id, len(addition.added))
    return replace(answer, status="queued" if busy else "running")
