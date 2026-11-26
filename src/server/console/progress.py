"""Following a run the console launched: which operations start one, where to read its state, and what to show of it
(state, counters, a progress bar when there is a total, the last error) until it ends or waits for an actor."""

from collections.abc import Mapping
from dataclasses import dataclass

from .bodies import JsonObject, JsonValue, text_of
from .catalog import Operation

REFRESH = 2.0  # seconds between two reads of the run
# (module, method, path) of what starts or moves a run → where its state is read ({id}: the run's id).
WATCHED: dict[tuple[str, str, str], str] = {
    ("ingesta", "POST", "/runs"): "/ingesta/runs/{id}",
    ("parsing", "POST", "/runs"): "/parsing/runs/{id}",
    ("parsing", "POST", "/runs/{id}/cancel"): "/parsing/runs/{id}",  # until it ends its current document (056)
    ("chunking", "POST", "/experiments"): "/chunking/experiments/{id}",
    ("chunking", "POST", "/experiments/{id}/resume"): "/chunking/experiments/{id}",
    ("chunking", "POST", "/experiments/{id}/documents"): "/chunking/experiments/{id}",  # adds and chunks (062)
    ("chunking", "POST", "/runs"): "/chunking/runs/{id}",
    ("chunking", "POST", "/runs/{id}/resume"): "/chunking/runs/{id}",
    ("chunking", "POST", "/runs/{id}/cancel"): "/chunking/runs/{id}",
    ("embeddings", "POST", "/runs"): "/embeddings/runs/{id}",
    ("embeddings", "POST", "/runs/{id}/cancel"): "/embeddings/runs/{id}",
    ("embeddings", "POST", "/experiments"): "/embeddings/experiments/{id}",
    ("embeddings", "POST", "/experiments/{id}/resume"): "/embeddings/experiments/{id}",  # feature 062
    ("embeddings", "POST", "/runs/{id}/resume"): "/embeddings/runs/{id}",  # feature 062
    ("llm", "POST", "/models/pull"): "/llm/models/pulls/{id}",
    ("pipeline", "POST", "/runs"): "/pipeline/runs/{id}",
    ("pipeline", "POST", "/runs/{id}/stages/{stage}/decision"): "/pipeline/runs/{id}",
    ("pipeline", "POST", "/runs/{id}/stages/{stage}/complete"): "/pipeline/runs/{id}",
    ("pipeline", "POST", "/runs/{id}/resume"): "/pipeline/runs/{id}",
}
ENDED = frozenset(
    {"terminada", "fallida", "interrumpida", "finished", "partial", "failed", "done", "cancelled", "interrupted"}
)
FAILED = frozenset({"fallida", "interrumpida", "failed", "cancelled", "interrupted"})
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
    "parsed": "parseados",
    "partial": "parciales",
    "missing": "sin RAW",
    "resumed": "reanudados",
    "unparsed": "sin parseo",
    "documents": "documentos",
    "embedded": "embebidos",
    "unchanged": "sin cambios",
    "added": "agregados",
    "already": "ya estaban",
}
_EMBEDDINGS_DONE = ("embedded", "unchanged", "skipped", "missing", "errors")  # what an embeddings run went over


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


def _fraction(progress: JsonObject, body: JsonObject) -> float | None:
    for done, of in (("copiados", "total"), ("done", "files"), ("done", "total")):  # the last: parsing
        if done in progress and _number(progress.get(of)) > 0:  # parsing has `total` but no `copiados`
            return min(1.0, _number(progress.get(done)) / _number(progress.get(of)))
    if "unchanged" in progress and _number(progress.get("total")) > 0:  # embeddings: `done` isn't sent
        return min(1.0, sum(_number(progress.get(key)) for key in _EMBEDDINGS_DONE) / _number(progress.get("total")))
    documents = body.get("sha256s")
    if "unparsed" in progress and isinstance(documents, list) and documents:  # a chunking run
        finished = sum(_number(progress.get(key)) for key in ("chunked", "skipped", "unparsed", "errors"))
        return min(1.0, finished / len(documents))
    return None


def _last_error(body: JsonObject) -> str:
    if body.get("error"):
        return text_of(body.get("error"))
    for key in ("errores", "failures"):
        failures = body.get(key)
        if isinstance(failures, list) and failures and isinstance(failures[-1], dict):
            last = failures[-1]
            where = text_of(last.get("origen") or last.get("origin") or last.get("sha256"))
            return f"{where}: {text_of(last.get('error'))}" if where else text_of(last.get("error"))
    return ""


def _published(body: JsonValue) -> str:
    """What an ended ingestion left in data as RAW (feature 042), or why it couldn't."""
    result = body.get("resultado") if isinstance(body, dict) else None
    raw = result.get("en_data") if isinstance(result, dict) else None
    if not isinstance(raw, dict):
        return ""
    if raw.get("aviso"):
        return f"data: {text_of(raw.get('aviso'))}"
    counts = (
        ("subidos", "subidos"),
        ("ya_estaban", "ya estaban"),
        ("retirados", "retirados"),
        ("fallidos", "fallidos"),
    )
    return "data: " + ", ".join(f"{_number(raw.get(key))} {label}" for key, label in counts)


def _parts(body: JsonObject) -> tuple[str, float | None]:
    """A pipeline run by parts (feature 056): «parte i/n» and the share of parts done."""
    found = body.get("parts")
    parts = [p for p in found if isinstance(p, dict)] if isinstance(found, list) else []
    if not parts:
        return "", None
    done = sum(1 for p in parts if p.get("status") == "done")
    current = next((p for p in parts if p.get("status") in ("running", "failed", "cancelled")), None)
    at = _number(current.get("index")) if current else done
    return f"parte {at}/{len(parts)} ({done} hechas)", done / len(parts)


def snapshot(body: JsonValue) -> Snapshot:
    """What to show of a run's state (any of the four kinds)."""
    if not isinstance(body, dict):
        return Snapshot("?", (), None, "", "no se pudo leer la corrida")
    status = text_of(body.get("estado") or body.get("status"))
    raw = body.get("progreso") or body.get("progress")
    progress = raw if isinstance(raw, dict) else {}
    counters = tuple((LABELS.get(name, name), str(value)) for name, value in progress.items() if isinstance(value, int))
    note = ""
    if body.get("stage"):
        note = f"etapa: {text_of(body.get('stage'))}"
    waiting = body.get("waiting")
    if isinstance(waiting, dict) and waiting.get("actor"):
        note += f" · espera a {text_of(waiting.get('actor'))}"
    published = _published(body)
    if published:
        note = f"{note} · {published}" if note else published
    parts, share = _parts(body)
    if parts:
        note = f"{note} · {parts}" if note else parts
    if body.get("cancel_requested") and status in ("queued", "running"):
        note = (
            f"{note} · cancelando: termina el documento actual" if note else "cancelando: termina el documento actual"
        )
    fraction = _fraction(progress, body)
    return Snapshot(status, counters, share if fraction is None else fraction, note, _last_error(body))


def bar(fraction: float, width: int) -> str:
    filled = round(fraction * width)
    return "█" * filled + "░" * (width - filled) + f" {fraction:4.0%}"
