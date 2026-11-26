"""Free JSON fields of a body that the console shows key by key (feature 062).

`files` and `params` of POST /pipeline/runs are free objects in the OpenAPI (the pipeline checks them with its own
messages), so catalog.py can only offer them as one JSON field. Here they get their known keys, named as catalog.py
would flatten them: `files.sha256s`, `files.pages.from`, `params.chunkear.extend`, `params.embeber.models`... Only a
field the OpenAPI publishes as JSON is expanded: if a module types it, its own flattened fields are used instead.
What the form doesn't offer (another template's params) still goes with F5 (edit the JSON): apply_body keeps the
keys nobody filled in.
"""

from dataclasses import replace

from .catalog import Field, Kind, Operation

type Place = tuple[str, str, str, str]  # (module, method, path inside the module, field)

CHUNKERS = ("hybrid", "hierarchical", "page")


def _field(name: str, kind: Kind, description: str, repeated: bool = False, default: str = "") -> Field:
    choices = CHUNKERS if kind == "choice" else ()
    return Field(name, "body", kind, repeated=repeated, choices=choices, default=default, description=description)


def _selection(prefix: str, from_run: bool) -> tuple[Field, ...]:
    """The keys of a selection of documents (spec 062): one mode and the filters of their RAW."""
    found = [
        _field(f"{prefix}all", "boolean", "modo: todos los documentos (con los filtros)", default="false"),
        _field(f"{prefix}sha256s", "text", "modo: esta lista de documentos", repeated=True),
        _field(f"{prefix}pages.from", "integer", "modo páginas: la primera (con per_page)"),
        _field(f"{prefix}pages.to", "integer", "modo páginas: la última"),
        _field(f"{prefix}per_page", "integer", "documentos por página (solo con pages)"),
        _field(f"{prefix}sample", "integer", "modo muestra: cuántos al azar (después de los filtros)"),
        _field(f"{prefix}seed", "integer", "semilla de la muestra: con ella se repite (solo con sample)"),
    ]
    if from_run:
        found.append(_field(f"{prefix}from_run", "text", "modo: el lote de otra corrida del pipeline"))
    found += [
        _field(f"{prefix}types", "text", "filtro: tipos (pdf, docx, doc)", repeated=True),
        _field(f"{prefix}year", "integer", "filtro: año"),
        _field(f"{prefix}month", "integer", "filtro: mes, 1 a 12 (con year)"),
        _field(f"{prefix}week", "text", "filtro: semana (con month)"),
    ]
    return tuple(found)


_CHUNKEAR = "params.chunkear"
_PARAMS = (
    _field(f"{_CHUNKEAR}.experiment.name", "text", "experimentos: un experimento de chunking nuevo, con este nombre"),
    _field(f"{_CHUNKEAR}.experiment.description", "text", "experimentos: su descripción"),
    _field(f"{_CHUNKEAR}.experiment.chunking.chunker", "choice", "experimentos: el chunker (hybrid por defecto)"),
    _field(f"{_CHUNKEAR}.experiment.chunking.tokenizer", "text", "experimentos: el tokenizador (uno solo)"),
    _field(f"{_CHUNKEAR}.experiment.chunking.max_tokens", "integer", "experimentos: tokens por chunk (hybrid)"),
    _field(f"{_CHUNKEAR}.experiment.chunking.merge_peers", "boolean", "experimentos: unir vecinos (hybrid)"),
    _field(f"{_CHUNKEAR}.extend", "text", "experimentos: agregar a este experimento de chunking lo que no tiene"),
    _field(f"{_CHUNKEAR}.official", "boolean", "experimentos: sin chunking, los FRAGMENTOS oficiales", default="false"),
    _field("params.embeber.models", "text", "experimentos: los modelos de embeddings (uno o varios)", repeated=True),
    _field("params.laboratorio", "json", "laboratorio: {chunking, embeddings, llm} del ciclo"),
)

EXPANDED: dict[Place, tuple[Field, ...]] = {
    ("pipeline", "POST", "/runs", "files"): _selection("files.", from_run=True),
    ("pipeline", "POST", "/runs", "params"): _PARAMS,
    ("data", "POST", "/documents/select", "files"): _selection("files.", from_run=False),
}


def expand(operation: Operation) -> Operation:
    """The operation with its known free objects shown key by key."""
    fields: list[Field] = []
    for item in operation.fields:
        found = EXPANDED.get((operation.module.name, operation.method, operation.path, item.name))
        fields += found if found is not None and item.kind == "json" else (item,)
    return operation if tuple(fields) == operation.fields else replace(operation, fields=tuple(fields))
