"""GET /health: whether Docling is installed and whether ingesta and data answer (over HTTP, as chunking uses them)."""

from fastapi import APIRouter

from chunking.api.app_info import VERSION
from chunking.api.dependencies import DocumentConverter, Probe, Settings
from chunking.api.schemas import HealthStatus, ServiceState

router = APIRouter(tags=["health"])


def _state(answers: bool) -> ServiceState:
    return "ok" if answers else "unavailable"


@router.get("/health")
def health(settings: Settings, probe: Probe, converter: DocumentConverter) -> HealthStatus:
    # Synchronous route: it runs in a thread, so the server is free to answer the requests it makes to itself.
    installed = converter.available()
    ingesta = probe.responds(f"{settings.ingesta_path}/health")
    data = probe.responds(f"{settings.data_path}/health")
    return HealthStatus(
        status="ok" if installed and ingesta and data else "degraded",
        version=VERSION,
        docling="installed" if installed else "missing",
        docling_version=converter.version(),
        ingesta=_state(ingesta),
        data=_state(data),
    )
