"""Pipeline HTTP API (FastAPI, feature 028), mounted by server at /pipeline.

Presentation layer: builds the adapters behind the ports and drives the domain's Engine with an Executor (one worker
thread per module queue). Routes live in routes/, one per file, registered in routes.ROUTERS.
"""

from .app import create_app
from .dependencies import ApiSettings

__all__ = ["ApiSettings", "create_app"]
