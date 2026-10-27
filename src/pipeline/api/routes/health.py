"""GET /health: whether the modules the pipeline calls answer."""

from fastapi import APIRouter

from pipeline.adapters import responds
from pipeline.api.app_info import VERSION
from pipeline.api.dependencies import Settings
from pipeline.api.schemas import PipelineHealth

router = APIRouter(tags=["health"])


@router.get("/health")
def health(settings: Settings) -> PipelineHealth:
    """Always 200; `degraded` if ingesta, chunking or data (or Neo4j behind it) doesn't answer."""
    paths = {"ingesta": settings.ingesta_path, "chunking": settings.chunking_path, "data": settings.data_path}
    modules = {
        name: "ok" if responds(settings.self_url, f"{path}/health") else "unavailable" for name, path in paths.items()
    }
    healthy = all(status == "ok" for status in modules.values())
    return PipelineHealth("ok" if healthy else "degraded", VERSION, modules)
