"""GET /health: whether the modules consultas calls answer."""

from fastapi import APIRouter

from consultas.adapters import responds
from consultas.api.app_info import VERSION
from consultas.api.dependencies import Settings
from consultas.api.schemas import HealthStatus

router = APIRouter(tags=["health"])


@router.get("/health")
def health(settings: Settings) -> HealthStatus:
    """Always 200; `degraded` if embeddings, llm or data (or Neo4j behind it) doesn't answer. `parsing` only serves
    the attached documents only: without it the rest works, so it doesn't degrade."""
    # Synchronous route: it runs in a thread, so the server is free to answer the requests it makes to itself.
    paths = {
        "embeddings": settings.embeddings_path,
        "llm": settings.llm_path,
        "data": settings.data_path,
        "parsing": settings.parsing_path,
    }
    states = {name: responds(settings.self_url, f"{path}/health") for name, path in paths.items()}
    return HealthStatus(
        status="ok" if states["embeddings"] and states["llm"] and states["data"] else "degraded",
        version=VERSION,
        embeddings="ok" if states["embeddings"] else "unavailable",
        llm="ok" if states["llm"] else "unavailable",
        data="ok" if states["data"] else "unavailable",
        parsing="ok" if states["parsing"] else "unavailable",
    )
