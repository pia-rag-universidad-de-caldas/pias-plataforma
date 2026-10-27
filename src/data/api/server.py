"""ASGI server startup (called by the `prueba-chunking-data serve` command)."""

import uvicorn

from data.models import GraphAdapter

from .app import create_app
from .dependencies import ApiSettings


def serve(settings: ApiSettings, graph: GraphAdapter, host: str, port: int) -> None:
    uvicorn.run(create_app(settings, graph), host=host, port=port)
