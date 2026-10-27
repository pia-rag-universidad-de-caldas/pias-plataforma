"""The values a field can take, read from what exists (the console's autocomplete): node ids of the label chosen,
experiments, runs, documents, scores, templates and their stages, actors, and ingesta's origins and sha256. What was
created in this session comes first.

The filters of ingesta's chunkable files (type, year, month, week, code; in GET /ingesta/data and in the files of a
chunking run or experiment) are facets: each one offers only the values that still give files with the OTHER filters
already chosen, with how many (read from every page of GET /ingesta/data, kept per combination of filters).

Each rule says for which module and field (and, when the name is ambiguous, for which path) and where to read the
values; everything is read over HTTP from the same server.
"""

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from chunking.config import TOKENIZERS  # the only ones a run may ask for (they are downloaded from the Hub)

from .bodies import JsonObject, JsonValue
from .catalog import Field, Operation
from .client import ApiClient

MAX_SUGGESTIONS = 500
KNOWN_ACTORS = ("lab", "lab2", "embeber", "modelscenter")  # the pipeline's actors (feature 028)
MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
          "noviembre", "diciembre")  # fmt: skip


FILTERS = {"type": "type", "types": "type", "year": "year", "month": "month", "week": "week", "code": "code"}
COLUMNS = {"type": "tipo", "year": "anio", "month": "mes_num", "week": "semana", "code": "codigo"}  # by query param
PAGE = 500  # ingesta's MAX_PER_PAGE


@dataclass(frozen=True)
class Suggestion:
    value: str
    detail: str = ""


@dataclass(frozen=True)
class Options:
    items: list[Suggestion]
    source: str  # where they were read: a route of the API, or the console itself


def _ordered(value: str) -> tuple[int, str]:
    """Numbers in numeric order, the rest alphabetically."""
    return (int(value), "") if value.isdigit() else (1 << 62, value)


type Recent = Mapping[tuple[str, str], list[str]]  # (module, resource) → ids created in the session, newest first
type Reader = Callable[["Suggester", Operation, Mapping[str, str]], list[Suggestion]]


def _objects(value: JsonValue) -> list[JsonObject]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _text(value: JsonValue) -> str:
    return "" if value is None else str(value)


def _detail(row: JsonObject, *names: str) -> str:
    return " · ".join(_text(row.get(name)) for name in names if row.get(name) not in (None, ""))


def _name_of(properties: JsonValue) -> str:
    """A node's most telling property, to show next to its id."""
    if not isinstance(properties, dict):
        return ""
    for name in ("nombre", "name", "titulo", "estado", "status", "origen"):
        if properties.get(name) not in (None, ""):
            return _text(properties.get(name))
    return ""


class Suggester:
    def __init__(self, client: ApiClient, recent: Recent) -> None:
        self._client = client
        self._recent = recent
        self._source = ""
        self._matching: dict[tuple[tuple[str, str], ...], list[JsonObject]] = {}

    # facets of ingesta's chunkable files

    def _filters(self, item: Field, values: Mapping[str, str]) -> list[tuple[str, str]]:
        """The other filters already chosen in the form, as GET /ingesta/data's query."""
        prefix = item.name.rpartition(".")[0]
        prefix = f"{prefix}." if prefix else ""
        own = FILTERS[item.name.split(".")[-1]]
        query: list[tuple[str, str]] = []
        for name, param in FILTERS.items():
            if param == own:
                continue
            query += [(param, part.strip()) for part in values.get(prefix + name, "").split(",") if part.strip()]
        return sorted(set(query))

    def files_matching(self, query: list[tuple[str, str]]) -> list[JsonObject]:
        """Every chunkable file that passes the filters (all the pages), kept for the session."""
        key = tuple(query)
        if key not in self._matching:
            rows: list[JsonObject] = []
            page, pages = 1, 1
            while page <= pages:
                body = self._get("/ingesta/data", [*query, ("per_page", str(PAGE)), ("page", str(page))])
                if not isinstance(body, dict):
                    break
                rows += _objects(body.get("archivos"))
                total = body.get("paginas")
                pages = total if isinstance(total, int) else 0
                page += 1
            self._matching[key] = rows
        return self._matching[key]

    def facet(self, _: Operation, values: Mapping[str, str], item: Field) -> list[Suggestion]:
        query = self._filters(item, values)
        column = COLUMNS[FILTERS[item.name.split(".")[-1]]]
        counts = Counter(_text(row.get(column)) for row in self.files_matching(query))
        chosen = ", ".join(f"{name}={value}" for name, value in query) or "sin otros filtros"
        self._source = f"GET /ingesta/data ({chosen}; todas las páginas): solo los valores que dan resultados"
        found = []
        for value in sorted((v for v in counts if v), key=_ordered):
            month = (
                f"{MONTHS[int(value) - 1]} · "
                if column == "mes_num" and value.isdigit() and 0 < int(value) < 13
                else ""
            )
            found.append(Suggestion(value, f"{month}{counts[value]} archivos"))
        return found

    def _get(self, path: str, params: Mapping[str, str] | Sequence[tuple[str, str]] | None = None) -> JsonValue:
        return self._client.get_json(path, params or {})

    # ingesta

    def _files(self) -> list[JsonObject]:
        body = self._get("/ingesta/data", {"per_page": str(MAX_SUGGESTIONS)})
        return _objects(body.get("archivos")) if isinstance(body, dict) else []

    def years(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        self._source = "GET /ingesta/stats/years"
        body = self._get("/ingesta/stats/years")
        rows = _objects(body.get("filas_anios")) if isinstance(body, dict) else []
        return [Suggestion(_text(row.get("anio")), f"{_text(row.get('archivos'))} archivos") for row in rows]

    def types(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        self._source = "GET /ingesta/stats/types"
        body = self._get("/ingesta/stats/types")
        names = body.get("tipos") if isinstance(body, dict) else None
        return [Suggestion(_text(name)) for name in names] if isinstance(names, list) else []

    def origins(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        self._source = "GET /ingesta/data (primeros 500)"
        return [Suggestion(_text(row.get("origen")), _text(row.get("tipo"))) for row in self._files()]

    def sha256s(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        self._source = "GET /ingesta/data (primeros 500)"
        return [Suggestion(_text(row.get("sha256")), _text(row.get("origen"))) for row in self._files()]

    def ingestions(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        self._source = "GET /ingesta/runs"
        rows = _objects(self._get("/ingesta/runs"))
        return [Suggestion(_text(row.get("id")), _detail(row, "estado", "inicio")) for row in rows]

    # data

    def _nodes(self, label: str) -> list[Suggestion]:
        self._source = "GET /data/nodes/{label}"
        if not label:
            return []
        body = self._get(f"/data/nodes/{label}", {"per_page": str(MAX_SUGGESTIONS)})
        rows = _objects(body.get("nodes")) if isinstance(body, dict) else []
        return [Suggestion(_text(row.get("id")), _name_of(row.get("properties"))) for row in rows]

    def node_ids(self, _: Operation, values: Mapping[str, str]) -> list[Suggestion]:
        return self._nodes(values.get("label", ""))

    def source_ids(self, _: Operation, values: Mapping[str, str]) -> list[Suggestion]:
        return self._nodes(values.get("source_label") or values.get("source.label", ""))

    def target_ids(self, _: Operation, values: Mapping[str, str]) -> list[Suggestion]:
        return self._nodes(values.get("target_label") or values.get("target.label", ""))

    # chunking

    def experiments(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        self._source = "GET /chunking/experiments"
        rows = _objects(self._get("/chunking/experiments"))
        return [Suggestion(_text(row.get("id")), _detail(row, "name", "status", "created")) for row in rows]

    def chunking_runs(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        self._source = "GET /chunking/runs"
        rows = _objects(self._get("/chunking/runs"))
        return [Suggestion(_text(row.get("id")), _detail(row, "status", "started")) for row in rows]

    def documents(self, operation: Operation, values: Mapping[str, str]) -> list[Suggestion]:
        self._source = "GET /chunking/documents o /chunking/experiments/{id}/documents"
        if operation.path.startswith("/experiments/") and values.get("id"):
            rows = _objects(self._get(f"/chunking/experiments/{values['id']}/documents"))
            return [Suggestion(_text(row.get("sha256")), _detail(row, "name", "status")) for row in rows]
        body = self._get("/chunking/documents", {"per_page": str(MAX_SUGGESTIONS)})
        rows = _objects(body.get("documents")) if isinstance(body, dict) else []
        return [Suggestion(_text(row.get("sha256")), _detail(row, "origin", "status")) for row in rows]

    def scores(self, _: Operation, values: Mapping[str, str]) -> list[Suggestion]:
        self._source = "GET /chunking/experiments/{id}/scores"
        if not values.get("id"):
            return []
        body = self._get(f"/chunking/experiments/{values['id']}/scores")
        rows = _objects(body.get("scores")) if isinstance(body, dict) else []
        return [Suggestion(_text(row.get("id")), _detail(row, "author", "created")) for row in rows]

    def tokenizers(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        self._source = "consola: TOKENIZERS de chunking/config (los únicos que una corrida acepta)"
        return [Suggestion(name) for name in TOKENIZERS]

    # pipeline

    def templates(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        self._source = "GET /pipeline/pipelines"
        rows = _objects(self._get("/pipeline/pipelines"))
        return [Suggestion(_text(row.get("id")), _detail(row, "name")) for row in rows]

    def pipeline_runs(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        self._source = "GET /pipeline/runs"
        rows = _objects(self._get("/pipeline/runs"))
        return [Suggestion(_text(row.get("id")), _detail(row, "name", "status", "stage")) for row in rows]

    def stages(self, operation: Operation, values: Mapping[str, str]) -> list[Suggestion]:
        self._source = "GET /pipeline/runs/{id} o /pipeline/pipelines/{id} (sus etapas)"
        owner = values.get("id", "")
        if not owner:
            return []
        if operation.path.startswith("/runs/"):
            run = self._get(f"/pipeline/runs/{owner}")
            stages = run.get("template") if isinstance(run, dict) else None
            waiting = _text(run.get("stage")) if isinstance(run, dict) else ""
        else:
            stages, waiting = self._get(f"/pipeline/pipelines/{owner}"), ""
        rows = _objects(stages.get("stages")) if isinstance(stages, dict) else []
        found = [Suggestion(_text(row.get("id")), _detail(row, "action", "actor")) for row in rows]
        return sorted(found, key=lambda item: item.value != waiting)  # the stage it is at first

    def actors(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        self._source = "GET /pipeline/actors y los actores conocidos del pipeline"
        rows = _objects(self._get("/pipeline/actors"))
        names = [_text(row.get("name")) for row in rows] + list(KNOWN_ACTORS)
        return [Suggestion(name) for name in dict.fromkeys(names) if name]

    # the rules

    def _is_filter(self, operation: Operation, item: Field) -> bool:
        """A filter of ingesta's chunkable files: in GET /ingesta/data, a chunking run or an experiment's files."""
        name, prefix = item.name.split(".")[-1], item.name.rpartition(".")[0]
        if name not in FILTERS or item.kind not in ("text", "integer"):
            return False
        module, path = operation.module.name, operation.path
        return (
            (module == "ingesta" and path == "/data")
            or (module == "chunking" and path == "/runs" and not prefix)
            or (module == "chunking" and path == "/experiments" and prefix == "files")
        )

    def _reader(self, operation: Operation, item: Field) -> Reader | None:
        module, path, name = operation.module.name, operation.path, item.name.split(".")[-1]
        prefix = item.name.split(".")[0]
        if self._is_filter(operation, item):
            return lambda suggester, op, values: suggester.facet(op, values, item)
        if module == "ingesta":
            readers: dict[str, Reader] = {
                "year": Suggester.years,
                "file_type": Suggester.types,
                "origin": Suggester.origins,
                "sha256": Suggester.sha256s,
            }
            if name == "id" and path.startswith("/runs/"):
                return Suggester.ingestions
            return readers.get(name)
        if module == "data":
            if name == "id" and path.startswith("/nodes/"):
                return Suggester.node_ids
            if (name == "source_id") or (prefix == "source" and name == "id"):
                return Suggester.source_ids
            if (name == "target_id") or (prefix == "target" and name == "id"):
                return Suggester.target_ids
            return None
        if module == "chunking":
            if name == "id" and path.startswith("/runs/"):
                return Suggester.chunking_runs
            if name in ("id", "ids", "from_experiment"):
                return Suggester.experiments
            if name == "score_id":
                return Suggester.scores
            if name == "sha256" and item.location == "path":
                return Suggester.documents
            if name == "sha256s":
                return Suggester.sha256s
            if name == "tokenizer":
                return Suggester.tokenizers
            return None
        if module == "pipeline":
            if name == "id":
                return Suggester.pipeline_runs if path.startswith("/runs") else Suggester.templates
            if name in ("stage", "before", "after"):
                return Suggester.stages
            if name in ("actor", "name") and (path.startswith("/actors") or name == "actor"):
                return Suggester.actors
            if name == "template":
                return Suggester.templates
            if name == "types":
                return Suggester.types
        return None

    def supports(self, operation: Operation, item: Field) -> bool:
        return item.kind not in ("boolean", "choice") and self._reader(operation, item) is not None

    def values(self, operation: Operation, item: Field, current: Mapping[str, str]) -> Options:
        """What exists for the field (recent ones first), given what the form has so far, and where it was read."""
        reader = self._reader(operation, item)
        if reader is None:
            return Options([], "")
        self._source = ""
        found = reader(self, operation, current)
        recent = self._recent.get((operation.module.name, operation.segment), []) if item.name == "id" else []
        first = [Suggestion(value, "creado en esta sesión") for value in recent]
        known = {item.value for item in first}
        items = (first + [s for s in found if s.value and s.value not in known])[:MAX_SUGGESTIONS]
        return Options(items, self._source)
