"""GET /health: whether Ollama answers (and its version) and whether data answers."""

from fastapi import APIRouter

from common.http import responds
from llm.api.app_info import VERSION
from llm.api.dependencies import Settings
from llm.api.schemas import HealthStatus
from llm.config import HTTP_TIMEOUT
from llm.models import ModelsDown

router = APIRouter(tags=["health"])


@router.get("/health")
def health(settings: Settings) -> HealthStatus:
    # Synchronous route: it runs in a thread, so the server is free to answer the request it makes to itself.
    try:
        with settings.ollama(HTTP_TIMEOUT) as ollama:
            found: str | None = ollama.version()
    except ModelsDown:
        found = None
    data = responds(settings.self_url, f"{settings.data_path}/health")
    return HealthStatus(
        status="ok" if found is not None and data else "degraded",
        version=VERSION,
        ollama="ok" if found is not None else "unavailable",
        ollama_version=found,
        ollama_url=settings.ollama_url,
        data="ok" if data else "unavailable",
    )
