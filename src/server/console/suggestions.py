"""The values a field can take, read from what exists (the console's autocomplete): node ids of the label chosen,
experiments, chunking runs, parsed documents, embedding models, templates and their stages, actors, and ingesta's
origins and sha256. What
was created in this session comes first.

The filters of ingesta's chunkable files (type, year, month, week, code; in GET /ingesta/data) are facets: each one
offers only the values that still give files with the OTHER filters already chosen, with how many (read from every
page of GET /ingesta/data, kept per combination of filters).

Each rule says for which module and field (and, when the name is ambiguous, for which path) and where to read the
values; everything is read over HTTP from the same server.
"""

import json
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from chunking.config import TOKENIZERS  # the only ones chunking accepts (they are downloaded from the Hub)
from common.config import MAX_PER_PAGE
from llm.config import MODELS as LLM_MODELS  # the admitted ones, if Ollama doesn't answer GET /llm/models

from .bodies import JsonObject, JsonValue, text_of
from .catalog import Field, Operation
from .client import ApiClient

MAX_SUGGESTIONS = 500
PARSED_SUGGESTIONS = 500  # read without their document (?omit=documento)
KNOWN_ACTORS = ("lab",)  # the pipeline's actors (feature 044: the laboratory's only one)
MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
          "noviembre", "diciembre")  # fmt: skip


FILTERS = {"type": "type", "types": "type", "year": "year", "month": "month", "week": "week", "code": "code"}
COLUMNS = {"type": "tipo", "year": "anio", "month": "mes_num", "week": "semana", "code": "codigo"}  # by query param
PAGE = MAX_PER_PAGE
SELECT_PAGE = min(MAX_SUGGESTIONS, MAX_PER_PAGE)


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


def _json_object(value: JsonValue) -> JsonObject:
    """A property kept as JSON text (a run's `detalle`) as an object; {} if it isn't one."""
    if isinstance(value, dict):
        return value
    try:
        parsed: JsonValue = json.loads(value) if isinstance(value, str) else None
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _detail(row: JsonObject, *names: str) -> str:
    return " · ".join(text_of(row.get(name)) for name in names if row.get(name) not in (None, ""))


def _name_of(properties: JsonValue) -> str:
    """A node's most telling property, to show next to its id."""
    if not isinstance(properties, dict):
        return ""
    for name in ("nombre", "name", "titulo", "estado", "status", "origen"):
        if properties.get(name) not in (None, ""):
            return text_of(properties.get(name))
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
        counts = Counter(text_of(row.get(column)) for row in self.files_matching(query))
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
        return [Suggestion(text_of(row.get("anio")), f"{text_of(row.get('archivos'))} archivos") for row in rows]

    def types(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        self._source = "GET /ingesta/stats/types"
        body = self._get("/ingesta/stats/types")
        names = body.get("tipos") if isinstance(body, dict) else None
        return [Suggestion(text_of(name)) for name in names] if isinstance(names, list) else []

    def origins(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        self._source = "GET /ingesta/data (primeros 500)"
        return [Suggestion(text_of(row.get("origen")), text_of(row.get("tipo"))) for row in self._files()]

    def sha256s(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        self._source = "GET /ingesta/data (primeros 500)"
        return [Suggestion(text_of(row.get("sha256")), text_of(row.get("origen"))) for row in self._files()]

    def raws(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        """The files ingesta published in data (feature 042), without their content."""
        self._source = "GET /data/nodes/RAW?omit=contenido (primeros 500)"
        body = self._get("/data/nodes/RAW", [("omit", "contenido"), ("per_page", str(PAGE))])
        rows = _objects(body.get("nodes")) if isinstance(body, dict) else []
        return [Suggestion(text_of(row.get("id")), _name_of(row.get("properties"))) for row in rows]

    def _missing(self, stage: str, params: Sequence[tuple[str, str]], what: str) -> list[Suggestion]:
        """The sha256s data says are still missing in a stage (GET /data/progress/<stage>?list=missing), the first
        MAX_SUGGESTIONS, with how many are missing in all."""
        query = [("list", "missing"), ("per_page", str(min(MAX_SUGGESTIONS, MAX_PER_PAGE))), *params]
        body = self._get(f"/data/progress/{stage}", query)
        found = body.get("sha256s") if isinstance(body, dict) else None
        missing = text_of(body.get("missing")) if isinstance(body, dict) else "?"
        self._source = f"GET /data/progress/{stage}?list=missing ({missing} {what}; primeros {MAX_SUGGESTIONS})"
        return [Suggestion(text_of(sha256), what) for sha256 in found] if isinstance(found, list) else []

    def unparsed(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        """The current RAW not parsed with parsing's configuration yet (feature 057): what a run would parse."""
        config = self._get("/parsing/config")
        fingerprint = text_of(config.get("fingerprint")) if isinstance(config, dict) else ""
        return self._missing("parsing", [("fingerprint", fingerprint)] if fingerprint else [], "sin parsear")

    def parsing_runs(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        self._source = "GET /parsing/runs"
        rows = _objects(self._get("/parsing/runs"))
        return [Suggestion(text_of(row.get("id")), _detail(row, "status", "requested")) for row in rows]

    def ingestions(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        self._source = "GET /ingesta/runs"
        rows = _objects(self._get("/ingesta/runs"))
        return [Suggestion(text_of(row.get("id")), _detail(row, "estado", "inicio")) for row in rows]

    # data

    def _nodes(self, label: str) -> list[Suggestion]:
        self._source = "GET /data/nodes/{label}"
        if not label:
            return []
        body = self._get(f"/data/nodes/{label}", {"per_page": str(MAX_SUGGESTIONS)})
        rows = _objects(body.get("nodes")) if isinstance(body, dict) else []
        return [Suggestion(text_of(row.get("id")), _name_of(row.get("properties"))) for row in rows]

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
        return [Suggestion(text_of(row.get("id")), _detail(row, "name", "status", "created")) for row in rows]

    def chunking_runs(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        self._source = "GET /chunking/runs"
        rows = _objects(self._get("/chunking/runs"))
        return [Suggestion(text_of(row.get("id")), _detail(row, "status", "requested")) for row in rows]

    def parsed(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        return self.parsed_documents()

    def parsed_documents(self) -> list[Suggestion]:
        """The JSON of data: what parsing left (feature 042), the only documents chunking can take."""
        self._source = f"GET /data/nodes/JSON?omit=documento (primeros {PARSED_SUGGESTIONS})"
        body = self._get("/data/nodes/JSON", [("omit", "documento"), ("per_page", str(PARSED_SUGGESTIONS))])
        rows = _objects(body.get("nodes")) if isinstance(body, dict) else []
        found = []
        for row in rows:
            raw = row.get("properties")
            properties = raw if isinstance(raw, dict) else {}
            found.append(Suggestion(text_of(row.get("id")), _detail(properties, "estado", "estado_chunking")))
        return found

    def unchunked(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        """The parsed JSON not chunked with the active configuration yet (feature 057): what a run would chunk."""
        config = self._get("/chunking/config")
        fingerprint = text_of(config.get("fingerprint")) if isinstance(config, dict) else ""
        return self._missing("chunking", [("fingerprint", fingerprint)] if fingerprint else [], "sin chunkear")

    def tokenizers(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        self._source = "consola: TOKENIZERS de chunking/config (los únicos que chunking acepta)"
        return [Suggestion(name) for name in TOKENIZERS]

    # embeddings (feature 046)

    def models(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        """The embedding models with their dimension and limit (and, feature 062, the tokens a chunk can have)."""
        self._source = "GET /embeddings/models"
        rows = _objects(self._get("/embeddings/models"))
        found = []
        for row in rows:
            budget = row.get("default_passage_budget")
            parts = (
                f"{text_of(row.get('dimensions'))} dim",
                f"hasta {text_of(row.get('max_tokens'))} tokens",
                f"chunk de hasta {budget}" if isinstance(budget, int) else "",
                "por defecto" if row.get("default") is True else "",
            )
            found.append(Suggestion(text_of(row.get("name")), " · ".join(part for part in parts if part)))
        return found

    def _vector_property(self, model: str) -> str:
        """The property of a model's vectors (GET /embeddings/models); the active one's if no model is given."""
        if model:
            rows = _objects(self._get("/embeddings/models"))
            return next((text_of(r.get("vector_property")) for r in rows if text_of(r.get("name")) == model), "")
        config = self._get("/embeddings/config")
        return text_of(config.get("vector_property")) if isinstance(config, dict) else ""

    def chunked(self, operation: Operation, values: Mapping[str, str]) -> list[Suggestion]:
        """The JSON chunking left chunked: the only ones a run of embeddings embeds."""
        found = [s for s in self.parsed(operation, values) if "fragmentado" in s.detail]
        self._source += ", solo los chunkeados"
        return found

    def unembedded(self, _: Operation, values: Mapping[str, str]) -> list[Suggestion]:
        """The chunked JSON without the vectors of the run's model (the one of the form, or the active one) over their
        current chunks (feature 057): what a run would embed."""
        property = self._vector_property(values.get("model", ""))
        if not property:
            self._source = "GET /embeddings/config (sin la propiedad del modelo: ¿un servidor anterior a la 057?)"
            return []
        return self._missing("embeddings", [("property", property)], "sin embeber")

    def finished_experiments(self, operation: Operation, values: Mapping[str, str]) -> list[Suggestion]:
        """The chunking experiments whose chunks an embeddings experiment can take: the finished ones and (feature
        059) the partial ones."""
        found = [s for s in self.experiments(operation, values) if "finished" in s.detail or "partial" in s.detail]
        self._source += ", solo los terminados o parciales"
        return found

    def embedding_runs(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        self._source = "GET /embeddings/runs"
        rows = _objects(self._get("/embeddings/runs"))
        return [Suggestion(text_of(row.get("id")), _detail(row, "status", "requested")) for row in rows]

    def embedding_experiments(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        self._source = "GET /embeddings/experiments"
        rows = _objects(self._get("/embeddings/experiments"))
        return [Suggestion(text_of(row.get("id")), _detail(row, "name", "status", "requested")) for row in rows]

    # what is missing to an experiment (feature 062), read from data

    def _selected(self, exclude: str, what: str) -> list[Suggestion] | None:
        """The parsed documents (POST /data/documents/select, universe parsed), without those of the chunking
        experiment `exclude`; None if data doesn't have the route (a server before feature 062)."""
        body: JsonObject = {"universe": "parsed", "files": {"all": True}, "page": 1, "per_page": SELECT_PAGE}
        if exclude:
            body["exclude_experiment"] = exclude
        found = self._client.post_json("/data/documents/select", body)
        if not isinstance(found, dict):
            return None
        sha256s = found.get("sha256s")
        without = f" sin los de {exclude}" if exclude else ""
        self._source = (
            f"POST /data/documents/select (universe parsed{without}): faltan {text_of(found.get('total'))} "
            f"({what}; primeros {SELECT_PAGE})"
        )
        return [Suggestion(text_of(sha256), what) for sha256 in sha256s] if isinstance(sha256s, list) else []

    def experiment_documents(self, experiment: str) -> list[str]:
        """The sha256s a chunking experiment has, read from data: its EXP_DOCUMENTO (`<experiment>:<sha256>`) or,
        before feature 059, its EXP_USA to a JSON."""
        rows = _objects(self._get(f"/data/nodes/EXPERIMENTO/{experiment}/relationships"))
        found: dict[str, None] = {}
        for row in rows:
            target = row.get("target")
            if not isinstance(target, dict) or text_of(target.get("id")) == experiment:
                continue
            label, key = text_of(target.get("label")), text_of(target.get("id"))
            if label == "EXP_DOCUMENTO":
                found[key.rpartition(":")[2]] = None
            elif label == "JSON":
                found[key] = None
        return list(found)

    def not_in_experiment(self, experiment: str, what: str) -> list[Suggestion]:
        """The parsed documents a chunking experiment doesn't have yet."""
        if not experiment:
            self._source = "elige primero el experimento de chunking"
            return []
        selected = self._selected(experiment, what)
        if selected is not None:
            return selected
        have = set(self.experiment_documents(experiment))
        found = [s for s in self.parsed_documents() if s.value not in have]
        self._source = (
            f"GET /data/nodes/JSON?omit=documento (primeros {PARSED_SUGGESTIONS}) sin los {len(have)} de {experiment} "
            f"(GET /data/nodes/EXPERIMENTO/{experiment}/relationships): faltan {len(found)} ({what})"
        )
        return found

    def missing_to_experiment(self, _: Operation, values: Mapping[str, str]) -> list[Suggestion]:
        """POST /chunking/experiments/{id}/documents: the parsed documents the experiment doesn't have."""
        return self.not_in_experiment(values.get("id", ""), "parseados que no tiene")

    def missing_vectors(self, _: Operation, values: Mapping[str, str]) -> list[Suggestion]:
        """POST /embeddings/experiments/{id}/resume: the documents of its chunking experiment without a vector of this
        one. Read from data: the EXP_EMBEDDINGS node (its `detalle`: the chunking experiment and what it embedded)
        and the documents of that chunking experiment."""
        id = values.get("id", "")
        if not id:
            self._source = "elige primero el experimento de embeddings"
            return []
        node = self._get(f"/data/nodes/EXP_EMBEDDINGS/{id}")
        properties = node.get("properties") if isinstance(node, dict) else None
        detail = _json_object(properties.get("detalle") if isinstance(properties, dict) else None)
        chunking = text_of(detail.get("chunking_experiment"))
        if not chunking:
            self._source = f"GET /data/nodes/EXP_EMBEDDINGS/{id} (no dice su experimento de chunking)"
            return []
        embedded = detail.get("embedded")
        done = {text_of(s) for s in embedded} if isinstance(embedded, list) else set()
        documents = self.experiment_documents(chunking)
        found = [Suggestion(s, f"de {chunking}, sin vector") for s in documents if s not in done]
        self._source = (
            f"GET /data/nodes/EXP_EMBEDDINGS/{id} y GET /data/nodes/EXPERIMENTO/{chunking}/relationships: "
            f"faltan {len(found)} de {len(documents)} (sin vector de este experimento)"
        )
        return found

    def pipeline_sha256s(self, operation: Operation, values: Mapping[str, str]) -> list[Suggestion]:
        """files.sha256s of POST /pipeline/runs, only what is missing (feature 062). With experimentos: the parsed
        documents (without those of the experiment it extends) or, with official, those missing the vectors of the
        first model chosen; with produccion and laboratorio, ingesta's chunkable files (what they select from)."""
        if (values.get("template", "") or "produccion") != "experimentos":
            return self.sha256s(operation, values)
        extend = values.get("params.chunkear.extend", "").strip()
        if extend:
            return self.not_in_experiment(extend, "parseados que no tiene")
        if values.get("params.chunkear.official", "") == "true":
            models = [part.strip() for part in values.get("params.embeber.models", "").split(",") if part.strip()]
            model = models[0] if models else ""
            property = self._vector_property(model)
            if not property:
                self._source = (
                    "GET /embeddings/models (sin la propiedad del modelo: elige uno en params.embeber.models)"
                )
                return []
            return self._missing("embeddings", [("property", property)], f"sin vectores de {model or 'el activo'}")
        selected = self._selected("", "parseados")
        return selected if selected is not None else self.parsed_documents()

    # llm (feature 047)

    def llm_models(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        """The admitted models, saying which Ollama has; if it doesn't answer, those of llm/config."""
        self._source = "GET /llm/models (admitted)"
        body = self._get("/llm/models")
        rows = _objects(body.get("admitted")) if isinstance(body, dict) else []
        if not rows:
            self._source = "consola: MODELS de llm/config (Ollama no respondió)"
            return [Suggestion(name, "visión" if spec.vision else "") for name, spec in LLM_MODELS.items()]
        found = []
        for row in rows:
            parts = (
                "descargado" if row.get("installed") else "sin descargar",
                "visión" if row.get("vision") else "",
                "por defecto" if row.get("default") else "",
            )
            found.append(Suggestion(text_of(row.get("name")), " · ".join(part for part in parts if part)))
        return found

    def llm_pulls(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        self._source = "GET /llm/models/pulls"
        rows = _objects(self._get("/llm/models/pulls"))
        return [Suggestion(text_of(row.get("id")), _detail(row, "model", "status", "requested")) for row in rows]

    # consultas (feature 048)
    def chats(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        self._source = "GET /consultas/chats"
        rows = _objects(self._get("/consultas/chats"))
        return [Suggestion(text_of(row.get("id")), _detail(row, "title", "modified")) for row in rows]

    def comparisons(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        self._source = "GET /consultas/comparisons"
        rows = _objects(self._get("/consultas/comparisons"))
        return [Suggestion(text_of(row.get("id")), _detail(row, "question", "created")) for row in rows]

    def finished_embedding_experiments(self, operation: Operation, values: Mapping[str, str]) -> list[Suggestion]:
        """The embeddings experiments a question can be asked to: the finished ones."""
        found = [s for s in self.embedding_experiments(operation, values) if "finished" in s.detail]
        self._source += ", solo los terminados"
        return found

    # pipeline

    def templates(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        self._source = "GET /pipeline/pipelines"
        rows = _objects(self._get("/pipeline/pipelines"))
        return [Suggestion(text_of(row.get("id")), _detail(row, "name")) for row in rows]

    def pipeline_runs(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        self._source = "GET /pipeline/runs"
        rows = _objects(self._get("/pipeline/runs"))
        return [Suggestion(text_of(row.get("id")), _detail(row, "name", "status", "stage")) for row in rows]

    def stages(self, operation: Operation, values: Mapping[str, str]) -> list[Suggestion]:
        self._source = "GET /pipeline/runs/{id} o /pipeline/pipelines/{id} (sus etapas)"
        owner = values.get("id", "")
        if not owner:
            return []
        if operation.path.startswith("/runs/"):
            run = self._get(f"/pipeline/runs/{owner}")
            stages = run.get("template") if isinstance(run, dict) else None
            waiting = text_of(run.get("stage")) if isinstance(run, dict) else ""
        else:
            stages, waiting = self._get(f"/pipeline/pipelines/{owner}"), ""
        rows = _objects(stages.get("stages")) if isinstance(stages, dict) else []
        found = [Suggestion(text_of(row.get("id")), _detail(row, "action", "actor")) for row in rows]
        return sorted(found, key=lambda item: item.value != waiting)  # the stage it is at first

    def actors(self, _: Operation, __: Mapping[str, str]) -> list[Suggestion]:
        self._source = "GET /pipeline/actors y los actores conocidos del pipeline"
        rows = _objects(self._get("/pipeline/actors"))
        names = [text_of(row.get("name")) for row in rows] + list(KNOWN_ACTORS)
        return [Suggestion(name) for name in dict.fromkeys(names) if name]

    # the rules

    def _is_filter(self, operation: Operation, item: Field) -> bool:
        """A filter of ingesta's chunkable files, in GET /ingesta/data."""
        name, prefix = item.name.split(".")[-1], item.name.rpartition(".")[0]
        if name not in FILTERS or item.kind not in ("text", "integer"):
            return False
        module, path = operation.module.name, operation.path
        return module == "ingesta" and path == "/data" and not prefix

    def _reader(self, operation: Operation, item: Field) -> Reader | None:
        if self._is_filter(operation, item):
            return lambda suggester, op, values: suggester.facet(op, values, item)
        rules = _RULES.get(operation.module.name)
        return rules(operation.path, item) if rules else None

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


def _ingesta_reader(path: str, item: Field) -> Reader | None:
    name = item.name.split(".")[-1]
    if name == "id" and path.startswith("/runs/"):
        return Suggester.ingestions
    readers: dict[str, Reader] = {
        "year": Suggester.years,
        "file_type": Suggester.types,
        "origin": Suggester.origins,
        "sha256": Suggester.sha256s,
    }
    return readers.get(name)


def _data_reader(path: str, item: Field) -> Reader | None:
    name, prefix = item.name.split(".")[-1], item.name.split(".")[0]
    if name == "id" and path.startswith("/nodes/"):
        return Suggester.node_ids
    if (name == "source_id") or (prefix == "source" and name == "id"):
        return Suggester.source_ids
    if (name == "target_id") or (prefix == "target" and name == "id"):
        return Suggester.target_ids
    if path == "/documents/select":  # feature 062
        readers: dict[str, Reader] = {
            "exclude_experiment": Suggester.experiments,
            "sha256s": Suggester.parsed,
            "types": Suggester.types,
            "year": Suggester.years,
        }
        return readers.get(name)
    return None


def _chunking_reader(path: str, item: Field) -> Reader | None:
    name = item.name.split(".")[-1]
    if name == "id" and path.startswith("/runs/"):
        return Suggester.chunking_runs
    readers: dict[str, Reader] = {
        "id": Suggester.experiments,
        "ids": Suggester.experiments,
        "from_experiment": Suggester.experiments,
        "sha256s": _CHUNKING_SHA256S.get(path, Suggester.parsed),
        "tokenizer": Suggester.tokenizers,
    }
    return readers.get(name)


_CHUNKING_SHA256S: dict[str, Reader] = {
    "/runs": Suggester.unchunked,
    "/experiments/{id}/documents": Suggester.missing_to_experiment,  # feature 062
}


def _pipeline_reader(path: str, item: Field) -> Reader | None:
    name = item.name.split(".")[-1]
    if name == "id":
        return Suggester.pipeline_runs if path.startswith("/runs") else Suggester.templates
    if name in ("actor", "name") and (path.startswith("/actors") or name == "actor"):
        return Suggester.actors
    readers: dict[str, Reader] = {
        "stage": Suggester.stages,
        "before": Suggester.stages,
        "after": Suggester.stages,
        "template": Suggester.templates,
        "types": Suggester.types,
        "year": Suggester.years,
        "sha256s": Suggester.pipeline_sha256s,  # feature 062: only what is missing
        "from_run": Suggester.pipeline_runs,
        "extend": Suggester.finished_experiments,
        "models": Suggester.models,
        "tokenizer": Suggester.tokenizers,
    }
    return readers.get(name)


def _parsing_reader(path: str, item: Field) -> Reader | None:
    name = item.name.split(".")[-1]
    if name == "id" and path.startswith("/runs/"):
        return Suggester.parsing_runs
    if name == "sha256s":
        return Suggester.unparsed if path == "/runs" else Suggester.raws
    return None


def _embeddings_reader(path: str, item: Field) -> Reader | None:
    name = item.name.split(".")[-1]
    if name == "id":
        return Suggester.embedding_runs if path.startswith("/runs") else Suggester.embedding_experiments
    readers: dict[str, Reader] = {
        "model": Suggester.models,
        "name": Suggester.models,  # DELETE /models/{name}/vectors (feature 055)
        "sha256s": _EMBEDDINGS_SHA256S.get(path, Suggester.chunked),
        "chunking_experiment": Suggester.finished_experiments,
    }
    return readers.get(name)


_EMBEDDINGS_SHA256S: dict[str, Reader] = {
    "/runs": Suggester.unembedded,
    "/experiments/{id}/resume": Suggester.missing_vectors,  # feature 062
}


def _llm_reader(path: str, item: Field) -> Reader | None:
    name = item.name.split(".")[-1]
    if name == "id" and path.startswith("/models/pulls"):
        return Suggester.llm_pulls
    return Suggester.llm_models if name in ("model", "name") else None


def _consultas_reader(path: str, item: Field) -> Reader | None:
    name = item.name.split(".")[-1]
    if name == "chat" or (name == "id" and path.startswith("/chats")):
        return Suggester.chats
    if name == "id" and path.startswith("/comparisons"):
        return Suggester.comparisons
    if name == "embeddings_model":
        return Suggester.models
    return Suggester.finished_embedding_experiments if name == "embeddings_experiment" else None


# Which values each module's fields can take, by the field and its route. A new one: a line in its function.
_RULES: dict[str, Callable[[str, Field], Reader | None]] = {
    "ingesta": _ingesta_reader,
    "data": _data_reader,
    "parsing": _parsing_reader,
    "chunking": _chunking_reader,
    "embeddings": _embeddings_reader,
    "llm": _llm_reader,
    "pipeline": _pipeline_reader,
    "consultas": _consultas_reader,
}
