"""Ingesta HTTP API (FastAPI, feature 016). With data/api/, the only package that imports fastapi and uvicorn (Ruff
TID251).

Presentation layer: builds the adapters, calls the domain and returns models; it has no business rules.
Routes live in routes/, one per file, registered in routes.ROUTERS.
"""

from .app import create_app
from .dependencies import ApiSettings

__all__ = ["ApiSettings", "create_app"]
