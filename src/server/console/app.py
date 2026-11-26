"""The console (features 034, 035, 039 and 054): gets Neo4j and Ollama (Docker Compose) and its own server ready,
then
home → module → resource → action → form → answer (a table, a run's live progress or coloured JSON). The home screen
leads to every process of the server, live; the services are asked at every step and what needs one that is off is
blocked; a route with nothing to fill in is sent at once.

Everything the console does to the modules goes through the server's HTTP API, the same one anybody else uses. Its
interface is in Spanish (feature 035).
"""

import signal
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from types import FrameType

from common.logs import quiet_logging
from ingesta.adapters import project_path

from . import texts
from .bodies import JsonValue
from .catalog import MODULES
from .client import ApiClient
from .docker_services import DockerServices
from .health import NEO4J, SERVER
from .live import summary
from .model_pulls import ModelPulls
from .navigation import Navigation
from .screen_types import Card
from .screens import Screens
from .server_process import ServerProcess
from .settings import COMPOSE_DIR, SERVER_LOG, ConsoleSettings
from .theme import plain
from .web_front import WEB, web_url

SERVER_TIMEOUT = 90.0  # seconds for the server to answer /health
STATUS_REFRESH = 2.0  # seconds between two looks at the services on the «estado» screen
MODELS_REFRESH = 1.0  # seconds between two looks at the models being pulled, on the home screen


def _number(body: JsonValue, key: str) -> str:
    value = body.get(key) if isinstance(body, dict) else None
    return str(value) if isinstance(value, int) else "?"


def _text(body: JsonValue, key: str) -> str:
    value = body.get(key) if isinstance(body, dict) else None
    return value if isinstance(value, str) else ""


class Console(Navigation):
    def _home_items(self) -> list[Card]:
        health = self._client.get_json("/health", {})
        modules = health.get("modules") if isinstance(health, dict) else None
        states = modules if isinstance(modules, dict) else {}

        def ok(name: str) -> bool:
            state = states.get(name)
            return isinstance(state, dict) and state.get("status") == "ok"

        files = _number(self._client.get_json("/ingesta/data", {"per_page": "1"}), "total")
        graph = self._health().active(NEO4J)  # without it, what reads the graph would only make this screen wait
        json_page = (
            self._client.get_json("/data/nodes/JSON", [("omit", "documento"), ("per_page", "1")]) if graph else None
        )
        documents = _number(json_page, "total") if graph else "?"
        documents = f" · {documents} documentos" if documents != "?" else ""
        parsing = self._client.get_json("/parsing/health", {})
        parsing_ready = isinstance(parsing, dict) and parsing.get("docling") == "installed"
        chunking = self._client.get_json("/chunking/health", {})
        docling = isinstance(chunking, dict) and chunking.get("docling_core") == "installed"
        embeddings = self._client.get_json("/embeddings/health", {})
        vectors = isinstance(embeddings, dict) and embeddings.get("models") == "installed"
        llm = self._client.get_json("/llm/health", {})
        ollama = isinstance(llm, dict) and llm.get("ollama") == "ok"
        ollama_version = _text(llm, "ollama_version")
        inbox = self._client.get_json("/pipeline/inbox", {}) if graph else None
        consultas = self._client.get_json("/consultas/health", {})
        consultas = consultas if isinstance(consultas, dict) else {}
        missing = [name for name in ("embeddings", "llm", "data") if consultas.get(name) != "ok"]
        waiting = len(inbox) if isinstance(inbox, list) else 0
        summaries = {
            "ingesta": (f"{files} archivos aptos", False) if files != "?" else ("sin memoria", True),
            "data": ("Neo4j responde", False) if ok("data") else ("Neo4j no responde", True),
            "parsing": (("Docling instalado", False) if parsing_ready else ("sin Docling", True)),
            "chunking": (("docling-core instalado", False) if docling else ("sin docling-core", True)),
            "embeddings": (("torch y transformers instalados", False) if vectors else ("sin torch", True)),
            "llm": ((f"Ollama {ollama_version} responde", False) if ollama else ("Ollama no responde", True)),
            "pipeline": (f"{waiting} esperando a un actor" if waiting else "nada esperando", False),
            "consultas": (f"no responde: {', '.join(missing)}", True) if missing else ("lista para preguntar", False),
        }
        sources = {
            "ingesta": "GET /ingesta/data (total)",
            "data": "GET /health (módulo data)",
            "parsing": "GET /parsing/health",
            "chunking": "GET /chunking/health y GET /data/nodes/JSON (total)",
            "embeddings": "GET /embeddings/health",
            "llm": "GET /llm/health",
            "pipeline": "GET /pipeline/inbox",
            "consultas": "GET /consultas/health",
        }
        processes = summary(self._client.get_json("/processes", {}))
        items = [
            Card(
                "procesos",
                processes,
                "Todos los procesos del servidor, en vivo. API: GET /processes y el WebSocket /processes/ws.",
            ),
            *(
                Card(
                    module.name,
                    summaries.get(module.name, ("", False))[0] + (documents if module.name == "chunking" else ""),
                    f"{texts.module(module.name).description}\nAPI: {module.prefix}/... · el resumen sale de "
                    f"{sources.get(module.name, f'GET {module.prefix}/health')}.",
                    status=ok(module.name),
                    alert=summaries.get(module.name, ("", False))[1],
                )
                for module in MODULES
            ),
        ]
        items.append(
            Card(
                WEB,
                "Chat, comparador de LLMs y experimentos en el navegador",
                f"Consola: abre el front web del servidor ({web_url(self._settings.url)}). No es un módulo.",
            )
        )
        items.append(Card("estado", "Qué servicios están activos", "Una tarjeta por servicio. API: GET /health."))
        items.append(
            Card(
                "salir",
                "Cierra la consola",
                "Consola: se cierra, apaga su servidor y detiene los servicios de Docker que arrancó ella "
                "(con --keep-docker los deja corriendo).",
            )
        )
        return items

    def _home_intro(self) -> str:
        line = self._models.line if self._models is not None else ""
        return f"Servidor {self._settings.url}" + (f" · {line}" if line else "")

    def _models_refresh(self, items: list[Card]) -> Callable[[], tuple[list[Card], str] | None]:
        """The models' progress in the home screen's intro, without asking the services again."""
        shown = [self._home_intro()]
        next_look = [time.monotonic() + MODELS_REFRESH]

        def renew() -> tuple[list[Card], str] | None:
            if time.monotonic() < next_look[0]:
                return None
            next_look[0] = time.monotonic() + MODELS_REFRESH
            intro = self._home_intro()
            if intro == shown[0]:
                return None
            shown[0] = intro
            return items, intro

        return renew

    def main(self) -> None:
        chosen = 0
        while True:
            items = self._home_items()
            event = self._screens.board(
                "prueba-chunking",
                self._home_intro(),
                items,
                chosen,
                escape=False,
                banner=True,
                refresh=self._models_refresh(items) if self._models is not None else None,
            )
            if event.kind != "card":
                continue
            picked = event.index
            if picked == len(items) - 1:
                return
            if not self._server.running:  # the console and its server live and die together
                tail = plain(self._server.tail(30))
                self._screens.show("El servidor se detuvo", f"Últimas líneas de {self._server.log}:\n\n{tail}")
                return
            chosen = picked
            if picked == 0:
                with self._at("procesos"):
                    self._processes("procesos", "/processes/ws")
            elif picked <= len(MODULES):
                with self._at(MODULES[picked - 1].name):
                    self._module(MODULES[picked - 1])
            elif picked == len(MODULES) + 1:
                with self._at(WEB):
                    self._web()
            else:
                with self._at("estado"):
                    self._status()

    def _service_cards(self) -> list[Card]:
        return [
            Card(
                service.name,
                "activo" if service.active else "desactivado",
                plain(self._started) if service.name == SERVER else "" if service.active else service.detail,
                status=service.active,
                alert=not service.active,
            )
            for service in self._health().services
        ]

    def _status(self) -> None:
        """A card per service: active or not, nothing else (feature 039); it renews itself."""
        next_look = [time.monotonic() + STATUS_REFRESH]

        def renew() -> tuple[list[Card], str] | None:
            if time.monotonic() < next_look[0]:
                return None
            next_look[0] = time.monotonic() + STATUS_REFRESH
            return self._service_cards(), "Se actualiza sola."

        while self._screens.board("estado", "Se actualiza sola.", self._service_cards(), refresh=renew).kind != "back":
            pass


def _closing_signals() -> tuple[signal.Signals, ...]:
    """Closing the terminal (SIGHUP, or SIGBREAK on Windows) and `kill` (SIGTERM)."""
    if sys.platform == "win32":
        return signal.SIGBREAK, signal.SIGTERM
    return signal.SIGHUP, signal.SIGTERM


@contextmanager
def _stopped_by_signals() -> Iterator[None]:
    """Closing the terminal or `kill` leave like Ctrl+C: the server and the Docker services are stopped on the way
    out."""

    def leave(number: int, _: FrameType | None) -> None:
        raise KeyboardInterrupt(signal.Signals(number).name)

    previous = {number: signal.signal(number, leave) for number in _closing_signals()}
    try:
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


@contextmanager
def _shielded() -> Iterator[None]:
    """While cleaning up, another Ctrl+C, SIGHUP or SIGTERM doesn't cut the cleaning in half."""
    numbers = (signal.SIGINT, *_closing_signals())
    previous = {number: signal.signal(number, signal.SIG_IGN) for number in numbers}
    try:
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def _say(line: str) -> None:
    """Prints, even with the terminal already closed (then there is nobody to read it)."""
    with suppress(OSError):
        print(line, flush=True)


def _wait_for(client: ApiClient, server: ServerProcess) -> bool:
    deadline = time.monotonic() + SERVER_TIMEOUT
    while time.monotonic() < deadline:
        if client.health() is not None:
            return True
        if not server.running:
            return False
        time.sleep(0.5)
    return False


def run_console(settings: ConsoleSettings) -> int:
    """Prepares the services (printing what it does), opens the console and cleans up when leaving: its server and
    the Docker services it started itself."""
    quiet_logging()
    client = ApiClient.to(settings.url)
    server: ServerProcess | None = None
    docker = DockerServices(settings, project_path(COMPOSE_DIR))
    models: ModelPulls | None = None
    notes: list[str] = []

    def report(line: str) -> None:
        _say(line)
        notes.append(line)

    try:
        with _stopped_by_signals():
            if client.health() is not None:
                print(
                    f"Ya hay algo respondiendo en {settings.url}: la consola usa su propio servidor, vivo solo "
                    "mientras ella lo está. Apaga el otro o elige otro puerto (--port 18000)."
                )
                return 1
            if settings.neo4j_password is None:
                report("Sin clave de Neo4j: el servidor arranca con /data respondiendo 503.")
            neo4j = docker.ensure(report)
            if settings.neo4j_password is not None:
                report(
                    neo4j.detail
                    if neo4j.ready
                    else f"Aviso: {neo4j.detail}; /data responde 503 y se reconecta cuando Neo4j responda."
                )
            server = ServerProcess(settings, project_path(SERVER_LOG))
            report(f"Arrancando el servidor en {settings.url} (salida en {server.log})...")
            server.start()
            if not _wait_for(client, server):
                print(f"El servidor no arrancó. Últimas líneas de {server.log}:\n{server.tail()}")
                return 1
            report("Servidor listo; se apaga al salir de la consola.")
            if docker.started:
                kept = "siguen corriendo al salir (--keep-docker)" if settings.keep_docker else "se detienen al salir"
                report(f"Arrancados por la consola: {', '.join(docker.started)}; {kept}.")
            models = ModelPulls(ApiClient.to(settings.url))
            models.start()
            with Screens.opened() as screens:
                Console(client, screens, settings, "\n".join(notes), server, models).main()
    except KeyboardInterrupt:
        pass
    finally:
        with _shielded():
            if models is not None:
                models.stop()
            client.close()
            if server is not None:
                _say("Apagando el servidor...")
                server.stop()
            docker.stop(_say)
    return 0
