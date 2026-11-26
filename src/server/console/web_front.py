"""The web front (052, 061, 063) from the console: not a module of the server, the console only opens it in the browser.

The server serves it at /web/; each screen is a hash (#chat, #comparar, #carga). Some console actions are better there
than in a form: asking (consultas «preguntar») opens the web chat.
"""

from dataclasses import dataclass

WEB = "web"
WEB_PATH = "/web/"


@dataclass(frozen=True)
class WebScreen:
    hash: str  # web/src/main.js: the screens
    name: str
    description: str


SCREENS = (
    WebScreen("chat", "chat", "Preguntas respondidas con los documentos, citando sus fuentes, y los chats guardados."),
    WebScreen("comparar", "comparar LLMs", "Una pregunta a hasta 4 LLMs y los experimentos de chunking y embeddings."),
    WebScreen("carga", "carga de documentos", "Subir documentos al corpus y seguir su procesamiento."),
)

# console actions that open a screen of the web instead of a form: (module, resource segment) → screen
OPENS_WEB = {("consultas", "ask"): "chat"}


def web_url(server_url: str, screen: str = "") -> str:
    """http://127.0.0.1:8000/web/#chat."""
    return f"{server_url.rstrip('/')}{WEB_PATH}" + (f"#{screen}" if screen else "")


def web_screen(module: str, segment: str) -> WebScreen | None:
    """The screen a console resource opens in the web, if it opens one."""
    hash = OPENS_WEB.get((module, segment))
    return next((s for s in SCREENS if s.hash == hash), None)
