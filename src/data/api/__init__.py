"""PIAA graph HTTP API (FastAPI, feature 018). With ingesta/api/, the only package that imports fastapi and uvicorn.

Presentation layer: builds the repository on top of the graph adapter and returns models; the schema rules live in
data.schema. Routes live in routes/, one per file, registered in routes.ROUTERS.
"""

from .app import create_app
from .dependencies import ApiSettings
from .server import serve

__all__ = ["ApiSettings", "create_app", "serve"]
