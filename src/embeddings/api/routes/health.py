"""GET /health: whether torch and transformers are installed (without loading a model) and whether data answers.
embeddings talks to no other module."""

from fastapi import APIRouter

from common.http import responds
from embeddings.api.app_info import VERSION
from embeddings.api.dependencies import Embedding, Settings
from embeddings.api.schemas import HealthStatus

router = APIRouter(tags=["health"])


@router.get("/health")
def health(settings: Settings, embedder: Embedding) -> HealthStatus:
    # Synchronous route: it runs in a thread, so the server is free to answer the request it makes to itself.
    installed = embedder.available()
    data = responds(settings.self_url, f"{settings.data_path}/health")
    return HealthStatus(
        status="ok" if installed and data else "degraded",
        version=VERSION,
        models="installed" if installed else "missing",
        data="ok" if data else "unavailable",
    )
