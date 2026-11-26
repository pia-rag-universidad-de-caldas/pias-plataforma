"""What the console offers: the modules and, read from each one's openapi.json, its operations and their fields.

The fields are never written by hand: path and query parameters, and every key of the body (nested objects
flattened as `parameters.max_tokens`), come with their type, allowed values and default as FastAPI publishes them. A
new route of a module shows up in the console by itself; texts.py only adds the Spanish names.
"""

import copy
from dataclasses import dataclass
from typing import Literal

from .bodies import JsonObject, JsonValue, template

type Kind = Literal["text", "integer", "number", "boolean", "choice", "json"]
type Location = Literal["path", "query", "body"]

_MAX_DEPTH = 8  # nested $ref/anyOf followed when reading a field's schema
_MAX_NESTING = 3  # body objects flattened into fields down to this depth; deeper ones are one JSON field


@dataclass(frozen=True)
class Module:
    name: str
    prefix: str  # where the server mounts it: /ingesta, /data...


MODULES = (
    Module("ingesta", "/ingesta"),
    Module("data", "/data"),
    Module("parsing", "/parsing"),
    Module("chunking", "/chunking"),
    Module("embeddings", "/embeddings"),
    Module("llm", "/llm"),
    Module("pipeline", "/pipeline"),
    Module("consultas", "/consultas"),
)


@dataclass(frozen=True)
class Field:
    """A path or query parameter, or one key of the body (`name` with dots for nested keys)."""

    name: str
    location: Location
    kind: Kind  # of each item when repeated
    required: bool = False
    repeated: bool = False  # a list: typed separated by commas (?name=a&name=b, or a JSON array in the body)
    choices: tuple[str, ...] = ()  # for kind "choice"
    default: str = ""
    description: str = ""

    @property
    def key(self) -> tuple[str, ...]:
        """Where it goes inside the body."""
        return tuple(self.name.split("."))


@dataclass(frozen=True)
class Operation:
    module: Module
    method: str
    path: str  # inside the module, as in its openapi.json: /runs/{id}
    summary: str
    description: str
    fields: tuple[Field, ...]
    body: JsonObject | None  # None: no body; otherwise the body to start from (a curated example or {})

    @property
    def writes(self) -> bool:
        return self.method != "GET"

    @property
    def segment(self) -> str:
        """The resource it belongs to: the first part of its path (`nodes` for /nodes/{label}/{id})."""
        parts = self.path.strip("/").split("/")
        return parts[0]

    def start_body(self) -> JsonObject | None:
        return None if self.body is None else copy.deepcopy(self.body)


def _object(value: JsonValue) -> JsonObject:
    return value if isinstance(value, dict) else {}


def _text(value: JsonValue) -> str:
    return value if isinstance(value, str) else ""


def _resolve(schema: JsonObject, components: JsonObject) -> JsonObject:
    """The schema with its $ref followed and its `anyOf: [X, null]` reduced to X."""
    for _ in range(_MAX_DEPTH):
        reference = _text(schema.get("$ref"))
        if reference:
            schema = _object(components.get(reference.rsplit("/", 1)[-1]))
            continue
        options = schema.get("anyOf")
        if isinstance(options, list):
            kept = [_object(option) for option in options if _object(option).get("type") != "null"]
            if len(kept) == 1:
                schema = kept[0]
                continue
        break
    return schema


def _default(value: JsonValue) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ",".join(_default(item) for item in value)
    return "" if value is None else str(value)


def _kind(schema: JsonObject) -> tuple[Kind, tuple[str, ...]]:
    enum = schema.get("enum")
    if isinstance(enum, list):
        return "choice", tuple(str(value) for value in enum)
    match schema.get("type"):
        case "boolean":
            return "boolean", ()
        case "integer":
            return "integer", ()
        case "number":
            return "number", ()
        case "string":
            return "text", ()
    return "json", ()


def _leaf(name: str, location: Location, raw: JsonObject, components: JsonObject, required: bool) -> Field:
    schema = _resolve(raw, components)
    repeated = schema.get("type") == "array"
    kind, choices = _kind(_resolve(_object(schema.get("items")), components) if repeated else schema)
    if repeated and kind == "json":  # a list of objects: one JSON value, not items separated by commas
        repeated = False
    return Field(
        name=name,
        location=location,
        kind=kind,
        required=required,
        repeated=repeated,
        choices=choices,
        default=_default(raw.get("default", schema.get("default"))),
        description=_text(raw.get("description")) or _text(schema.get("description")),
    )


def field(parameter: JsonObject, components: JsonObject) -> Field:
    """A Field from one entry of an operation's `parameters`."""
    location: Location = "path" if parameter.get("in") == "path" else "query"
    raw = _object(parameter.get("schema"))
    found = _leaf(_text(parameter.get("name")), location, raw, components, parameter.get("required") is True)
    description = _text(parameter.get("description"))
    if description and not found.description:
        return Field(**{**found.__dict__, "description": description})
    return found


def body_fields(
    schema: JsonObject, components: JsonObject, prefix: str = "", depth: int = 0, parent_required: bool = True
) -> list[Field]:
    """One field per key of an object body; objects with known keys are flattened (`files.pages.from`). A nested key is
    required only if its object is too: `source.id` is, `files.pages.from` isn't, because `pages` is optional."""
    resolved = _resolve(schema, components)
    properties = _object(resolved.get("properties"))
    required = resolved.get("required")
    needed = set(required) if isinstance(required, list) else set()
    found: list[Field] = []
    for name, raw in properties.items():
        child = _resolve(_object(raw), components)
        dotted = f"{prefix}{name}"
        is_required = name in needed and parent_required
        if child.get("type") == "object" and _object(child.get("properties")) and depth < _MAX_NESTING:
            found += body_fields(child, components, f"{dotted}.", depth + 1, is_required)
        else:
            found.append(_leaf(dotted, "body", _object(raw), components, is_required))
    return found


def _body(module: Module, method: str, path: str, operation: JsonObject, components: JsonObject) -> list[Field] | None:
    request = _object(operation.get("requestBody"))
    if not request:
        return None
    schema = _object(_object(_object(request.get("content")).get("application/json")).get("schema"))
    return body_fields(schema, components)


def operations(spec: JsonObject, module: Module) -> tuple[Operation, ...]:
    """Every operation of a module's openapi.json, in the order the module declares them."""
    components = _object(_object(spec.get("components")).get("schemas"))
    found: list[Operation] = []
    for path, methods in _object(spec.get("paths")).items():
        for method, raw in _object(methods).items():
            operation = _object(raw)
            parameters = operation.get("parameters")
            fields = [
                field(_object(parameter), components)
                for parameter in (parameters if isinstance(parameters, list) else [])
            ]
            verb = method.upper()
            body = _body(module, verb, path, operation, components)
            found.append(
                Operation(
                    module=module,
                    method=verb,
                    path=path,
                    summary=_text(operation.get("summary")),
                    description=_text(operation.get("description")),
                    fields=tuple(fields + (body or [])),
                    body=None if body is None else template(module.name, verb, path),
                )
            )
    return tuple(found)
