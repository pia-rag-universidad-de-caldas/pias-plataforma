"""Chunking experiments (feature 025): POST/GET /experiments, GET /experiments/compare, GET/DELETE /experiments/{id},
GET /experiments/{id}/documents[/{sha256}[/chunks]]; POST /experiments/{id}/promote (feature 028, to the official
graph). The record lives in the graph (experiment labels), read and
written through data over HTTP; the production graph is only touched by promote."""

import json
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import JsonValue

from chunking.adapters import HttpSession
from chunking.adapters.docling_converter import MISSING
from chunking.adapters.strategies import MISSING as NO_TRANSFORMERS
from chunking.api.dependencies import Chunker, DocumentConverter, Experiments, Registry, Settings, Store
from chunking.api.experiments import experiment_request
from chunking.api.experiments.registry import launch
from chunking.api.experiments.schemas import (
    ChunkView,
    ComparedView,
    DocumentView,
    ExperimentStarted,
    ExperimentSummary,
    ExperimentView,
    FileProblem,
    NewExperiment,
    PreviewFile,
    PromotionFailure,
    PromotionView,
    SectionView,
)
from chunking.config import CHUNK_PAGE_SIZE
from chunking.domain import (
    ExperimentGraph,
    ExperimentRunner,
    Promotion,
    Scoring,
    now,
)
from chunking.models import (
    ExperimentDocument,
    ExperimentRecord,
    ExperimentStatus,
    ExperimentStore,
    RunStatus,
    rule_name,
)
from common.api import Error

router = APIRouter(prefix="/experiments", tags=["experiments"])

type _Responses = dict[int | str, dict[str, object]]

_NOT_FOUND: _Responses = {404: {"model": Error, "description": "no experiment (or document) with that id"}}
_DOWN: _Responses = {503: {"model": Error, "description": "ingesta or data is not answering"}}


def _status(record: ExperimentRecord, active: str | None) -> ExperimentStatus:
    if record.status == ExperimentStatus.RUNNING and record.id != active:
        return ExperimentStatus.INTERRUPTED  # the server stopped while it ran
    return record.status


def _record(store: ExperimentStore, id: str) -> ExperimentRecord:
    record = store.experiment(id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"there is no experiment with id {id!r}")
    return record


def _loads(text: str | None) -> JsonValue:
    if text is None:
        return None
    loaded: JsonValue = json.loads(text)
    return loaded


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        200: {"model": ExperimentStarted, "description": "simulate: the files and the conversions it would reuse"},
        404: {"model": Error, "description": "from_experiment doesn't exist"},
        409: {"model": Error, "description": "an experiment or a production run is running"},
        422: {"model": Error, "description": "malformed files, conversion or plan"},
        503: {"model": Error, "description": "Docling missing (something to convert), or ingesta/data down"},
    },
)
def start_experiment(
    new: NewExperiment,
    response: Response,
    settings: Settings,
    store: Store,
    experiments: Experiments,
    runs: Registry,
    converter: DocumentConverter,
    chunker: Chunker,
) -> ExperimentStarted:
    """Validates, resolves the files, stores the EXPERIMENTO and runs it in the background (202). With `simulate`,
    only answers which files would enter and which conversions would be reused (200, nothing stored)."""
    request = experiment_request(new, converter.version() or "")
    if request.files.from_experiment:
        _record(store, request.files.from_experiment)
    id = uuid4().hex[:12]
    busy = any(r.status == RunStatus.RUNNING for r in runs.all())
    if not new.simulate and (busy or not experiments.start(id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "an experiment or a production run is still running")
    try:
        with HttpSession(settings.self_url, settings.ingesta_path, settings.data_path) as session:
            resolution = ExperimentRunner.resolve(session.source, store, request, CHUNK_PAGE_SIZE)
        to_convert = [f for f in resolution.files if not f.reused]
        if not new.simulate:
            if to_convert and not converter.available():
                raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, MISSING)
            if request.plan is not None and not chunker.available():
                raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, NO_TRANSFORMERS)
            store.save(ExperimentGraph.experiment(id, request, len(resolution.files), now()))
    except BaseException:
        experiments.done(id)
        raise
    answer = ExperimentStarted(
        id=None if new.simulate else id,
        status="simulated" if new.simulate else ExperimentStatus.RUNNING,
        files=[
            PreviewFile(f.document.sha256 or "", f.document.origin, f.document.name, f.reused) for f in resolution.files
        ],
        to_convert=len(to_convert),
        reused=len(resolution.files) - len(to_convert),
        failures=[FileProblem(f.error, f.origin, f.sha256) for f in resolution.failures],
    )
    if new.simulate:
        response.status_code = status.HTTP_200_OK
    else:
        launch(
            experiments,
            id,
            settings.self_url,
            settings.ingesta_path,
            settings.data_path,
            converter,
            chunker,
            request,
            resolution,
        )
    return answer


@router.get("", responses=_DOWN)
def list_experiments(store: Store, experiments: Experiments) -> list[ExperimentSummary]:
    """Every experiment in the graph (not only this session's), newest first."""
    active = experiments.active
    return [
        ExperimentSummary(r.id, r.name, r.description, _status(r, active), r.created, r.finished, r.progress)
        for r in store.experiments()
    ]


@router.get(
    "/compare",
    responses=_NOT_FOUND | _DOWN | {422: {"model": Error, "description": "fewer than two ids"}},
)
def compare_experiments(
    store: Store, ids: Annotated[list[str], Query(description="two or more: ?ids=a&ids=b")]
) -> list[ComparedView]:
    """Side by side: each experiment's request (conversion and plan), scores with their averages and the key numbers
    of its results."""
    unique = list(dict.fromkeys(ids))
    if len(unique) < 2:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "compare needs at least two different ids")
    compared = [Scoring.compare(_record(store, id), store.scores(id)) for id in unique]
    return [
        ComparedView(
            c.id, c.name, c.status, _loads(c.conversion_json), _loads(c.plan_json), c.scores, c.summary, c.results
        )
        for c in compared
    ]


@router.get("/{id}", responses=_NOT_FOUND | _DOWN)
def read_experiment(store: Store, experiments: Experiments, id: str) -> ExperimentView:
    r = _record(store, id)
    return ExperimentView(
        r.id,
        r.name,
        r.description,
        _status(r, experiments.active),
        r.created,
        r.finished,
        r.progress,
        _loads(r.files_json),
        _loads(r.conversion_json),
        _loads(r.plan_json),
        _loads(r.results_json),
        r.error,
    )


@router.post(
    "/{id}/promote",
    responses=_NOT_FOUND | _DOWN | {409: {"model": Error, "description": "the experiment is running or didn't finish"}},
)
def promote_experiment(store: Store, experiments: Experiments, id: str) -> PromotionView:
    """Copies an approved (finished) experiment to the official graph (feature 028). Conversion only: each converted
    document becomes its official JSON, (:PIAA)-[:ES]->(:JSON {contenido})-[:VIENE_DE]->(:EXP_DOCUMENTO), replacing
    the one it had. With a plan: its sections and chunks go under the official JSON as SECCION/FRAGMENTOS, replacing
    the ones it had. A document that can't be promoted is listed in `failed`; the rest are."""
    record = _record(store, id)
    if experiments.active == id or record.status != ExperimentStatus.FINISHED:
        raise HTTPException(status.HTTP_409_CONFLICT, f"the experiment is {_status(record, experiments.active)}")
    outcome = Promotion.run(store, record, now())
    failed = [PromotionFailure(f.sha256 or "", f.error) for f in outcome.failed]
    return PromotionView(outcome.experiment, outcome.kind, outcome.promoted, failed)


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_NOT_FOUND | _DOWN | {409: {"model": Error, "description": "it is running"}},
)
def delete_experiment(store: Store, experiments: Experiments, id: str) -> None:
    """Deletes the experiment, its sections, chunks and scores; the EXP_DOCUMENTO (shared conversions) stay."""
    if experiments.active == id:
        raise HTTPException(status.HTTP_409_CONFLICT, "the experiment is running")
    if not store.delete(id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"there is no experiment with id {id!r}")


def _document(store: ExperimentStore, id: str, sha256: str) -> ExperimentDocument:
    _record(store, id)
    found = next((d for d in store.documents(id) if d.sha256 == sha256), None)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"the experiment {id!r} has no document {sha256!r}")
    return found


@router.get("/{id}/documents", responses=_NOT_FOUND | _DOWN)
def experiment_documents(store: Store, id: str) -> list[ExperimentDocument]:
    """The documents of the experiment: whether their conversion was reused, status, sections and chunks."""
    _record(store, id)
    return store.documents(id)


@router.get("/{id}/documents/{sha256}", responses=_NOT_FOUND | _DOWN)
def experiment_document(store: Store, id: str, sha256: str) -> DocumentView:
    """One document: its conversion (parameters and JSON) and how each section was treated (rule, strategy...)."""
    document = _document(store, id, sha256)
    sections = [
        SectionView(
            s.index,
            s.title,
            s.level,
            s.pages,
            rule_name(s.rule),
            s.strategy,
            _loads(s.parameters_json),
            s.chunks,
            s.tokens,
        )
        for s in store.sections(id, document)
    ]
    conversion = _loads(store.conversion_json(document.conversion_id))
    return DocumentView(document, conversion, _loads(store.content(document.conversion_id)), sections)


@router.get("/{id}/documents/{sha256}/chunks", responses=_NOT_FOUND | _DOWN)
def experiment_chunks(store: Store, id: str, sha256: str) -> list[ChunkView]:
    """The chunks of the document in the experiment, by section and in order."""
    document = _document(store, id, sha256)
    chunks: list[ChunkView] = []
    counters: dict[int, int] = {}
    for section, piece in store.chunks(id, document):
        index = counters.get(section, 0)
        counters[section] = index + 1
        chunks.append(ChunkView(section, index, piece.text, piece.headings, piece.pages, piece.tokens))
    return chunks
