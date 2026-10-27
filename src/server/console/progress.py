"""Following a run the console launched: which operations start one, where to read its state, and what to show of it
(state, counters, a progress bar when there is a total, the last error) until it ends or waits for an actor."""

from collections.abc import Mapping
from dataclasses import dataclass

from .bodies import JsonObject, JsonValue
from .catalog import Operation

REFRESH = 2.0  # seconds between two reads of the run
# (module, method, path) of what starts or moves a run → where its state is read ({id}: the run's id).
WATCHED: dict[tuple[str, str, str], str] = {
    ("ingesta", "POST", "/runs"): "/ingesta/runs/{id}",
    ("chunking", "POST", "/runs"): "/chunking/runs/{id}",
    ("chunking", "POST", "/experiments"): "/chunking/experiments/{id}",
    ("pipeline", "POST", "/runs"): "/pipeline/runs/{id}",
    ("pipeline", "POST", "/runs/{id}/stages/{stage}/decision"): "/pipeline/runs/{id}",
    ("pipeline", "POST", "/runs/{id}/stages/{stage}/complete"): "/pipeline/runs/{id}",
    ("pipeline", "POST", "/runs/{id}/resume"): "/pipeline/runs/{id}",
}
ENDED = frozenset({"terminada", "fallida", "finished", "failed", "done", "cancelled", "interrupted"})
FAILED = frozenset({"fallida", "failed", "cancelled", "interrupted"})
WAITING = "waiting"
LABELS = {
    "copiados": "copiados",
    "total": "total",
    "pending": "pendientes",
    "chunked": "fragmentados",
    "chunks": "chunks",
    "skipped": "saltados",
    "errors": "errores",
    "files": "archivos",
    "done": "hechos",
    "converted": "convertidos",
    "reused": "reutilizados",
    "sections": "secciones",
}


@dataclass(frozen=True)
class Snapshot:
    status: str
    counters: tuple[tuple[str, str], ...]
    fraction: float | None  # 0..1 when the run has a total
    note: str  # the stage, or what it waits for
    error: str

    @property
    def ended(self) -> bool:
        return self.status in ENDED or self.status == WAITING

    @property
    def failed(self) -> bool:
        return self.status in FAILED


def watch_path(operation: Operation, run_id: str | None, values: Mapping[str, str]) -> str | None:
    """Where to read the run `operation` just started or moved; None if it doesn't start one (or was simulated)."""
    found = WATCHED.get((operation.module.name, operation.method, operation.path))
    identifier = values.get("id") if "{id}" in operation.path else run_id
    if found is None or not identifier:
        return None
    return found.replace("{id}", identifier)


def _number(value: JsonValue) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _text(value: JsonValue) -> str:
    return "" if value is None else str(value)


def _fraction(progress: JsonObject) -> float | None:
    for done, of in (("copiados", "total"), ("done", "files")):
        if _number(progress.get(of)) > 0:
            return min(1.0, _number(progress.get(done)) / _number(progress.get(of)))
    if "pending" in progress:  # chunking: what is left of what it found
        finished = sum(_number(progress.get(key)) for key in ("chunked", "skipped", "errors"))
        found = finished + _number(progress.get("pending"))
        return finished / found if found else None
    return None


def _last_error(body: JsonObject) -> str:
    if body.get("error"):
        return _text(body.get("error"))
    for key in ("errores", "failures"):
        failures = body.get(key)
        if isinstance(failures, list) and failures and isinstance(failures[-1], dict):
            last = failures[-1]
            where = _text(last.get("origen") or last.get("origin") or last.get("sha256"))
            return f"{where}: {_text(last.get('error'))}" if where else _text(last.get("error"))
    return ""


def snapshot(body: JsonValue) -> Snapshot:
    """What to show of a run's state (any of the four kinds)."""
    if not isinstance(body, dict):
        return Snapshot("?", (), None, "", "no se pudo leer la corrida")
    status = _text(body.get("estado") or body.get("status"))
    raw = body.get("progreso") or body.get("progress")
    progress = raw if isinstance(raw, dict) else {}
    counters = tuple((LABELS.get(name, name), str(value)) for name, value in progress.items() if isinstance(value, int))
    note = ""
    if body.get("stage"):
        note = f"etapa: {_text(body.get('stage'))}"
    waiting = body.get("waiting")
    if isinstance(waiting, dict) and waiting.get("actor"):
        note += f" · espera a {_text(waiting.get('actor'))}"
    return Snapshot(status, counters, _fraction(progress), note, _last_error(body))


def bar(fraction: float, width: int) -> str:
    filled = round(fraction * width)
    return "█" * filled + "░" * (width - filled) + f" {fraction:4.0%}"
