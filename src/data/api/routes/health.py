"""GET /health: the server answers and Neo4j accepts the credentials."""

from fastapi import APIRouter

from data.api.app_info import VERSION
from data.api.dependencies import Graph, Settings
from data.api.schemas import NEO4J_DOWN, HealthStatus, error

router = APIRouter(tags=["health"])


@router.get("/health", responses={503: error(NEO4J_DOWN)})
def health(settings: Settings, graph: Graph) -> HealthStatus:
    graph.verify()
    return HealthStatus(status="ok", version=VERSION, neo4j=settings.url)
