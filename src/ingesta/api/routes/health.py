"""GET /health: the server responds and the memory can be opened."""

from fastapi import APIRouter

from ingesta.adapters import visible_url
from ingesta.api.app_info import VERSION
from ingesta.api.dependencies import Memory, Settings
from ingesta.api.schemas import Error, HealthStatus

router = APIRouter(tags=["health"])


@router.get("/health", responses={503: {"model": Error, "description": "the memory could not be opened"}})
def health(config: Settings, _: Memory) -> HealthStatus:
    return HealthStatus(estado="ok", version=VERSION, memoria=visible_url(config.memory))
