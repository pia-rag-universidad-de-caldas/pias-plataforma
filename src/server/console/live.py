"""The board of processes as the console shows it (feature 039): read from the WebSocket of the server, a look between
two frames that never waits, and turned into cards."""

import json
from collections.abc import Mapping
from datetime import datetime
from types import TracebackType
from typing import Self
from urllib.parse import urlencode

from websockets.exceptions import WebSocketException
from websockets.sync.client import ClientConnection, connect

from .bodies import JsonObject, JsonValue
from .screen_types import Card

RETRY = 3.0  # seconds between two attempts to connect
OPEN_TIMEOUT = 1.0
WS_ALL = "/processes/ws"

STATES = {
    "queued": "en cola",
    "running": "en curso",
    "waiting": "esperando",
    "finished": "terminado",
    "failed": "falló",
    "cancelled": "cancelado",
    "interrupted": "interrumpido",
}
_KINDS = {"experiment": "experimento", "run": "corrida", "ingestion": "corrida"}
_NAMES = {"production run": "producción", "simulation": "simulación", "ingestion from folder": "desde la carpeta base"}
_COUNTS = (
    ("running", "en curso"),
    ("queued", "en cola"),
    ("waiting", "esperando"),
    ("finished", "terminados"),
    ("failed", "fallidos"),
    ("interrupted", "interrumpidos"),
    ("cancelled", "cancelados"),
)


def clock(seconds: int) -> str:
    """45 s · 3 min 20 s · 1 h 05 min."""
    if seconds < 60:
        return f"{seconds} s"
    minutes, rest = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} min {rest:02d} s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min"


def moment(text: JsonValue) -> str:
    """When, as a person reads it: 2026-11-06 14:03:21."""
    if not isinstance(text, str):
        return "?"
    try:
        return datetime.fromisoformat(text).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return text


def _alive(process: JsonObject) -> list[str]:
    parts: list[str] = []
    if process.get("position") is not None:
        parts.append(f"puesto {process['position']}")
    if process.get("total") is not None:
        parts.append(f"{process.get('done')}/{process['total']} ({process.get('percent')} %)")
    elapsed, remaining = process.get("elapsed_seconds"), process.get("remaining_seconds")
    if isinstance(elapsed, int):
        parts.append(f"lleva {clock(elapsed)}")
    if isinstance(remaining, int):
        parts.append(f"faltan ~{clock(remaining)}")
    strategies = process.get("strategies")
    if isinstance(strategies, list) and strategies:
        parts.append("con " + ", ".join(str(s) for s in strategies))
    if process.get("detail"):
        parts.append(str(process["detail"]).replace("stage ", "etapa ").replace(": waiting for ", ": espera a "))
    return parts


def _ended(process: JsonObject) -> list[str]:
    parts = [f"empezó {moment(process.get('started'))}", f"terminó {moment(process.get('finished'))}"]
    duration = process.get("duration_seconds")
    if isinstance(duration, int):
        parts.append(f"duró {clock(duration)}")
    if process.get("error"):
        parts.append(str(process["error"]))
    return parts


def process_card(process: JsonObject) -> Card:
    """What is going on with it while alive; once ended, only when it started, when it ended and how long it took."""
    state = str(process.get("state"))
    kind = str(process.get("kind"))
    name = _KINDS.get(kind, kind)
    if process.get("phase"):
        name += f" fase {process['phase']}"
    ended = process.get("finished") is not None or state in ("failed", "cancelled", "interrupted")
    text = [STATES.get(state, state), *(_ended(process) if ended else _alive(process))]
    return Card(
        f"{process.get('module')} · {name}: {_NAMES.get(str(process.get('name')), process.get('name'))}",
        " · ".join(text),
        f"id {process.get('id')} · Enter: ver el proceso.",
        status=False if state in ("failed", "interrupted") else True if state == "running" else None,
        alert=state in ("waiting", "queued"),
    )


def processes_of(board: JsonValue) -> list[JsonObject]:
    found = board.get("processes") if isinstance(board, dict) else None
    return [p for p in found if isinstance(p, dict)] if isinstance(found, list) else []


def summary(board: JsonValue) -> str:
    """How many in each state: those that have any, always the ones alive."""
    counts = board.get("counts") if isinstance(board, dict) else None
    if not isinstance(counts, dict):
        return "sin datos todavía"
    alive = ("running", "queued", "waiting")
    return " · ".join(
        f"{counts.get(state, 0)} {name}" for state, name in _COUNTS if state in alive or counts.get(state, 0)
    )


class ProcessFeed:
    """The last board the server sent. `read` never waits for it: it runs between two frames of the screen."""

    def __init__(self, url: str, path: str = WS_ALL, query: Mapping[str, str] | None = None) -> None:
        target = url.replace("http://", "ws://", 1).replace("https://", "wss://", 1) + path
        self.url = f"{target}?{urlencode(dict(query))}" if query else target
        self.board: JsonValue = None
        self.problem = ""
        self._socket: ClientConnection | None = None
        self._next_try = 0.0

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, kind: type[BaseException] | None, value: BaseException | None, trace: TracebackType | None
    ) -> None:
        self.close()

    def close(self) -> None:
        if self._socket is not None:
            self._socket.close()
            self._socket = None

    def _connect(self, now: float) -> None:
        if now < self._next_try:
            return
        try:
            self._socket = connect(self.url, open_timeout=OPEN_TIMEOUT)
            self.problem = ""
        except (OSError, TimeoutError, WebSocketException) as error:
            self.problem = f"sin conexión en vivo: {error}"
            self._next_try = now + RETRY

    def read(self, now: float) -> bool:
        """Takes what arrived; True if the board changed."""
        if self._socket is None:
            self._connect(now)
            if self._socket is None:
                return False
        changed = False
        try:
            while True:
                self.board = json.loads(self._socket.recv(timeout=0))
                changed = True
        except TimeoutError:
            return changed
        except (OSError, WebSocketException) as error:
            self.problem = f"se cortó la conexión en vivo: {error}"
            self._socket = None
            self._next_try = now + RETRY
            return True
