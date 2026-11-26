"""GET /health: whether docling-core is installed and whether data answers (over HTTP, as chunking uses it). Chunking
talks to no other module (feature 043)."""

from fastapi import APIRouter

from chunking.api.app_info import VERSION
from chunking.api.dependencies import DocumentChunker, Probe, Settings
from chunking.api.schemas import HealthStatus

router = APIRouter(tags=["health"])


@router.get("/health")
def health(settings: Settings, probe: Probe, chunker: DocumentChunker) -> HealthStatus:
    # Synchronous route: it runs in a thread, so the server is free to answer the request it makes to itself.
    installed = chunker.available()
    data = probe.responds(f"{settings.data_path}/health")
    return HealthStatus(
        status="ok" if installed and data else "degraded",
        version=VERSION,
        docling_core="installed" if installed else "missing",
        docling_core_version=chunker.version(),
        data="ok" if data else "unavailable",
    )
