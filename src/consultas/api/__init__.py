"""consultas HTTP API (FastAPI, feature 048), mounted by server at /consultas.

Presentation layer: builds the HTTP clients behind the ports and calls the domain's Asker. Routes live in routes/, one
per file, registered in routes.ROUTERS.
"""

from .app import create_app
from .dependencies import ApiSettings

__all__ = ["ApiSettings", "create_app"]
