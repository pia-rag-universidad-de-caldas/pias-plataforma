"""POST /runs (start a run in its own thread; one at a time), GET /runs and GET /runs/{id} (feature 023)."""

from uuid import uuid4

from fastapi import APIRouter, HTTPException, status

from chunking.adapters.docling_converter import MISSING
from chunking.api.dependencies import DocumentConverter, Experiments, Registry, Settings
from chunking.api.registry import launch, now
from chunking.api.schemas import Error, NewRun
from chunking.config import TOKENIZERS
from chunking.models import ChunkingParameters, ChunkingRun, DocumentFilter, RunRequest, RunStatus

router = APIRouter(tags=["runs"])


@router.post(
    "/runs",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        409: {"model": Error, "description": "another run is still running"},
        422: {
            "model": Error,
            "description": "invalid body or parameters (a tokenizer not in TOKENIZERS...)",
        },
        503: {"model": Error, "description": "Docling is not installed (uv sync --extra chunk)"},
    },
)
def start_run(
    settings: Settings, registry: Registry, experiments: Experiments, converter: DocumentConverter, new: NewRun
) -> ChunkingRun:
    """Starts a run in the background and answers at once; follow it with GET /runs/{id}. Each document is
    chunked with Docling and written to the graph (PIAA → JSON → SECCION → FRAGMENTOS) in one POST /data/batch,
    replacing what it had."""
    if not converter.available():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, MISSING)
    asked = new.parameters
    if asked.tokenizer not in TOKENIZERS:
        allowed = ", ".join(TOKENIZERS)
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"tokenizer {asked.tokenizer!r} isn't allowed; allowed: {allowed}"
        )
    parameters = ChunkingParameters(
        tokenizer=asked.tokenizer,
        max_tokens=asked.max_tokens,
        merge_peers=asked.merge_peers,
        repeat_table_header=asked.repeat_table_header,
        table_structure=asked.table_structure,
        table_mode=asked.table_mode,
        docling_version=converter.version() or "",
    )
    request = RunRequest(
        simulate=new.simulate,
        filter=DocumentFilter(new.types, new.year, new.month, new.week, new.code),
        limit=new.limit,
        retry_errors=new.retry_errors,
        sha256s=new.sha256s,
    )
    run = ChunkingRun(
        id=uuid4().hex[:12],
        status=RunStatus.RUNNING,
        started=now(),
        simulate=new.simulate,
        parameters=parameters,
        fingerprint=parameters.fingerprint,
    )
    if experiments.active is not None or not registry.start(run):
        raise HTTPException(status.HTTP_409_CONFLICT, "another chunking run (or an experiment) is still running")
    launch(registry, run, settings.self_url, settings.ingesta_path, settings.data_path, converter, request, parameters)
    return run


@router.get("/runs")
def list_runs(registry: Registry) -> list[ChunkingRun]:
    """The runs of this server session, newest first (they are not kept across restarts; the documents are)."""
    return registry.all()


@router.get("/runs/{id}", responses={404: {"model": Error, "description": "no run with that id"}})
def read_run(registry: Registry, id: str) -> ChunkingRun:
    run = registry.get(id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"there is no run with id {id!r}")
    return run
