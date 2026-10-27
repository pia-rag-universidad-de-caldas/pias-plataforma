"""GET /source and /runs (feature 030): check a source and run the ingestion from the API, like `organize` but never
moving: the source stays intact and the files are copied to ingesta/, registered and classified in the memory."""

import threading

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from ingesta.adapters import LocalFileAdapter, SQLORMAdapter, open_source, overlaps_ingest
from ingesta.api.dependencies import Settings
from ingesta.api.ingestion_registry import IngestionRegistry, work
from ingesta.api.schemas import Error, IngestionRun, IngestionSimulation, NewIngestion, PlannedCopy
from ingesta.domain import Ingestion, Naming
from ingesta.models import MemoryStoreError, OrganizationPlan, SourceCheck, SourceKind, SourceUnavailable
from ingesta.repository import DbCategoryRepository, DbFileRepository
from ingesta.tables import TABLES

router = APIRouter(tags=["ingestion"])

type _Responses = dict[int | str, dict[str, object]]  # `responses=` of a route

MAX_PLANNED = 50  # planned copies listed by a simulation

_UNAVAILABLE: _Responses = {501: {"model": Error, "description": "that kind of source is not available yet"}}


def _registry(request: Request) -> IngestionRegistry:
    registry: IngestionRegistry = request.app.state.ingestions
    return registry


def _processed(memory: str) -> set[str]:
    """The origins already in the memory; none if there is no memory yet (the run will create it)."""
    try:
        data = SQLORMAdapter.from_existing(memory, TABLES)
    except MemoryStoreError:
        return set()
    try:
        return DbFileRepository(data).processed_origins()
    finally:
        data.close()


def _check(config: Settings, kind: SourceKind) -> tuple[SourceCheck, OrganizationPlan | None]:
    """The check of the source: always the server's base folder (data/base/ unless `serve --base` says otherwise)."""
    location = config.base
    try:
        source = open_source(kind, location)
    except SourceUnavailable as e:
        raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, str(e)) from e
    return Ingestion.check(source, kind, _processed(config.memory), overlaps_ingest(kind, location, config.ingest))


def _simulation(config: Settings, check: SourceCheck, plan: OrganizationPlan) -> IngestionSimulation:
    planned = [PlannedCopy(f.path, f"{Naming.target_folder(f)}/{Naming.new_name(f)}") for f in plan.new[:MAX_PLANNED]]
    try:
        data = SQLORMAdapter.from_existing(config.memory, TABLES)
    except MemoryStoreError:  # no memory yet: nothing to relocate
        return IngestionSimulation(check, len(plan.new), planned, 0, {})
    try:
        placement = Ingestion.place(
            DbFileRepository(data), DbCategoryRepository(data), LocalFileAdapter(config.ingest), simulate=True
        )
    finally:
        data.close()
    return IngestionSimulation(check, len(plan.new), planned, len(placement.relocated), placement.main)


@router.get("/source", responses=_UNAVAILABLE)
def check_source(config: Settings, kind: SourceKind = SourceKind.FOLDER) -> SourceCheck:
    """Whether the source was found, what it has compared with the memory and why it can't be ingested, if so."""
    return _check(config, kind)[0]


@router.post(
    "/runs",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=IngestionRun,  # simulate and a failed check answer a JSONResponse of their own
    responses={
        200: {"model": IngestionSimulation, "description": "simulate: the check and what it would do"},
        409: {"model": Error, "description": "another ingestion is running"},
        422: {"model": SourceCheck, "description": "the source can't be ingested: its check says why"},
        **_UNAVAILABLE,
    },
)
def start_run(request: Request, config: Settings, body: NewIngestion | None = None) -> IngestionRun | Response:
    """Starts an ingestion in the background (202); GET /runs/{id} follows it. The source is never touched."""
    body = body or NewIngestion()
    check, plan = _check(config, body.source.kind)
    if not check.usable or plan is None:
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content=jsonable_encoder(check))
    if body.simulate:
        return JSONResponse(status_code=status.HTTP_200_OK, content=jsonable_encoder(_simulation(config, check, plan)))
    registry = _registry(request)
    run = registry.start(check, len(plan.new))
    if run is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "another ingestion is running")
    threading.Thread(target=work, args=(registry, run.id, config, plan), daemon=True, name=f"ingesta-{run.id}").start()
    return run


@router.get("/runs")
def list_runs(request: Request) -> list[IngestionRun]:
    """The ingestions of this server session, newest first (each one is also a row of `ejecuciones`)."""
    return _registry(request).all()


@router.get("/runs/{id}", responses={404: {"model": Error, "description": "no ingestion with that id"}})
def get_run(request: Request, id: str) -> IngestionRun:
    run = _registry(request).get(id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no ingestion {id}")
    return run
