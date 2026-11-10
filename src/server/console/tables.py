"""Lists in an answer shown as tables, and what a row gives to the actions that can be done with it.

A list is the answer itself (a JSON array of objects) or the one array of objects inside it (`archivos`, `nodes`,
`documents`...); `page`/`pages` (or `pagina`/`paginas`) make it paginated.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .bodies import JsonObject, JsonValue
from .catalog import Operation

MAX_COLUMNS = 6
MAX_WIDTH = 40
# The columns worth seeing first, by the name of the list (the rest keep the answer's order).
PREFERRED: dict[str, tuple[str, ...]] = {
    "archivos": ("nombre", "anio", "semana", "codigo", "tipo", "bytes"),
    "nodes": ("id",),
    "relationships": ("type", "source_label", "source_id", "target_label", "target_id"),
    "documents": ("sha256", "status", "code", "year", "chunks"),
    "": ("id", "name", "nombre", "status", "estado", "stage", "created", "inicio"),
}
_PAGE_KEYS = (("page", "pages"), ("pagina", "paginas"))
_SKIP = frozenset({"properties"})  # flattened as properties_<key> instead


@dataclass(frozen=True)
class Table:
    key: str  # where the list was ("" if the answer itself)
    columns: tuple[str, ...]
    rows: tuple[dict[str, str], ...]  # every column of each row (flattened), not only the shown ones
    page: int | None = None
    pages: int | None = None


def _cell(value: JsonValue) -> str:
    if isinstance(value, bool):
        return "sí" if value else "no"
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(_cell(item) for item in value)
    return str(value)


def flatten(row: JsonObject, prefix: str = "") -> dict[str, str]:
    """A row's values by name; nested objects as `<key>_<child>` (source.label → source_label)."""
    found: dict[str, str] = {}
    for name, value in row.items():
        if isinstance(value, dict):
            found.update(flatten(value, f"{prefix}{name}_"))
        else:
            found[f"{prefix}{name}"] = _cell(value)
    return found


def _list(body: JsonValue) -> tuple[str, list[JsonObject]] | None:
    if isinstance(body, list):
        rows = [row for row in body if isinstance(row, dict)]
        return ("", rows) if rows or not body else None
    if isinstance(body, dict):
        lists = [
            (key, value)
            for key, value in body.items()
            if isinstance(value, list) and value and all(isinstance(row, dict) for row in value)
        ]
        if len(lists) == 1:
            key, value = lists[0]
            return key, [row for row in value if isinstance(row, dict)]
    return None


def _columns(key: str, rows: Sequence[dict[str, str]]) -> tuple[str, ...]:
    seen: list[str] = []
    for row in rows:
        seen += [name for name in row if name not in seen]
    useful = [name for name in seen if any(len(row.get(name, "")) < 200 for row in rows)]
    first = [name for name in PREFERRED.get(key, PREFERRED[""]) if name in useful]
    rest = [name for name in useful if name not in first and name.split("_")[0] not in _SKIP]
    if key == "nodes":  # the node's own data are its properties
        rest = [name for name in useful if name.startswith("properties_")] + rest
    return tuple((first + rest)[:MAX_COLUMNS])


def table(body: JsonValue) -> Table | None:
    """The table of an answer that is a list, or None."""
    found = _list(body)
    if found is None:
        return None
    key, raw = found
    rows = tuple(flatten(row) for row in raw)
    page: int | None = None
    pages: int | None = None
    if isinstance(body, dict):
        for current, total in _PAGE_KEYS:
            if isinstance(body.get(current), int) and isinstance(body.get(total), int):
                page, pages = int(str(body[current])), int(str(body[total]))
    return Table(key, _columns(key, rows), rows, page, pages)


def width(table: Table, column: str) -> int:
    longest = max([len(column)] + [len(row.get(column, "")) for row in table.rows])
    return min(longest, MAX_WIDTH) + 2


_ALIASES = {"origin": "origen", "file_type": "tipo", "year": "anio", "code": "codigo"}
ROW_QUERY = frozenset({"origin"})  # query parameters a row also fills (ingesta: one file by its origin)


def _fillable(operation: Operation) -> list[str]:
    return [f.name for f in operation.fields if f.location == "path" or (f.location == "query" and f.name in ROW_QUERY)]


def row_values(row: Mapping[str, str], operation: Operation, current: Mapping[str, str]) -> dict[str, str] | None:
    """The values a row gives to `operation` (its path, and `origin`), completed with what the form had; None if a
    path value is missing. In a list of scores, the row's `id` is the `score_id` and the experiment stays `id`."""
    names = {f.name for f in operation.fields}
    values: dict[str, str] = {}
    for name in _fillable(operation):
        found = row.get(name) or row.get(_ALIASES.get(name, ""), "")
        if "score_id" in names and current.get("id"):
            found = row.get("id", "") if name == "score_id" else current["id"] if name == "id" else found
        found = found or current.get(name, "")
        if found:
            values[name] = found
        elif any(f.name == name and f.location == "path" for f in operation.fields):
            return None
    return values


def row_actions(source: Operation, candidates: Sequence[Operation]) -> list[Operation]:
    """The operations a row of `source`'s answer leads to: same resource, and they need more than `source` did."""
    taken = len(_fillable(source))
    return [op for op in candidates if op is not source and op.segment == source.segment and len(_fillable(op)) > taken]
