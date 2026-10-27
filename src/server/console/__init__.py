"""Interactive console (feature 034): `prueba-chunking` with no command. Starts Neo4j (Docker) and the server when
they are missing and lets every operation of the API be chosen, filled in and sent from menus (asciimatics).

The menus come from each module's openapi.json; the console only talks HTTP to the server.
"""

from .app import run_console
from .settings import ConsoleSettings

__all__ = ["ConsoleSettings", "run_console"]
