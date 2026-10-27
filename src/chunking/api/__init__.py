"""Chunking HTTP API (FastAPI, feature 021), mounted by server at /chunking.

Presentation layer: builds the adapters behind the ports and calls the domain. Routes live in routes/, one per file,
registered in routes.ROUTERS.
"""

from .app import create_app
from .dependencies import ApiSettings

__all__ = ["ApiSettings", "create_app"]
