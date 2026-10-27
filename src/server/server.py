"""ASGI server startup (called by the `prueba-chunking serve` command)."""

import uvicorn

from data.models import GraphAdapter

from .app import create_app
from .settings import ServerSettings


def serve(settings: ServerSettings, graph: GraphAdapter, host: str, port: int) -> None:
    """Serves every module; `graph` (from open_graph) is closed on shutdown by the root lifespan."""
    uvicorn.run(create_app(settings, graph), host=host, port=port)
