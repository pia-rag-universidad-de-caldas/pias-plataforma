"""ASGI server startup (called by the `prueba-chunking serve` command)."""

import uvicorn

from .app import create_app
from .dependencies import ApiSettings


def serve(settings: ApiSettings, host: str, port: int) -> None:
    uvicorn.run(create_app(settings), host=host, port=port)
