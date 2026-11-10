"""The progress screen of data (features 042 and 043): how many current files are parsed and how many parsed documents
are chunked, read from GET /data/progress/parsing and /chunking. Pure functions: what each card and list says."""

from dataclasses import dataclass

from .bodies import JsonObject, JsonValue
from .progress import bar
from .screen_types import Card

BAR_WIDTH = 20
MISSING_SHOWN = 200  # sha256s listed when a card is opened (the rest: page through GET /data/progress/...)
REFRESH = 3.0  # seconds between two reads while the screen is open


@dataclass(frozen=True)
class Stage:
    name: str
    path: str  # the data route
    over: str  # what `total` counts
    done: str  # what `done` means
    launch: str  # where the missing ones are processed


STAGES = (
    Stage("parseo", "/data/progress/parsing", "archivos vigentes (RAW)", "parseados", "POST /parsing/runs"),
    Stage("chunking", "/data/progress/chunking", "documentos parseados (JSON)", "con chunks", "POST /chunking/runs"),
)


def _number(body: JsonObject, key: str) -> int:
    value = body.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def card(stage: Stage, body: JsonValue) -> Card:
    """One stage: its bar, what is missing and why (partial, failed, never tried)."""
    if not isinstance(body, dict):
        return Card(stage.name, "no se pudo leer: ¿Neo4j responde?", f"API: GET {stage.path}", status=False)
    total, done, missing = _number(body, "total"), _number(body, "done"), _number(body, "missing")
    fraction = done / total if total else 1.0
    details = [f"{done} de {total} {stage.done}", f"faltan {missing}"]
    if stage.name == "parseo" and _number(body, "partial"):
        details.append(f"{_number(body, 'partial')} parciales")
    if _number(body, "errors"):
        details.append(f"{_number(body, 'errors')} con error")
    if _number(body, "never"):
        details.append(f"{_number(body, 'never')} sin intentar")
    return Card(
        f"{stage.name}: {stage.over}",
        f"{bar(fraction, BAR_WIDTH)}\n" + " · ".join(details),
        f"API: GET {stage.path} · Enter: ver los que faltan. Se procesan con {stage.launch}.",
        status=True if total and not missing else None,
        alert=_number(body, "errors") > 0,
    )


def missing_text(stage: Stage, body: JsonValue) -> str:
    """The missing sha256s of a stage, one per line, saying whether there are more than shown."""
    if not isinstance(body, dict):
        return f"No se pudo leer GET {stage.path}."
    found = body.get("sha256s")
    sha256s = [str(s) for s in found] if isinstance(found, list) else []
    missing = _number(body, "missing")
    if not sha256s:
        return f"No falta ninguno: todos los {stage.over} están {stage.done}."
    more = f"\n\n… y {missing - len(sha256s)} más (GET {stage.path}?page=2)." if missing > len(sha256s) else ""
    return f"Faltan {missing} ({stage.done} ya: {_number(body, 'done')}). Se procesan con {stage.launch}.\n\n" + (
        "\n".join(sha256s) + more
    )
