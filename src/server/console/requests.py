"""From what was typed in an operation's form to the HTTP request, or the first problem with it.

The body is a JSON object kept between the form and the JSON editor: `body_values` reads the form's fields out of it
and `apply_body` writes them back. A field left empty is removed (the API then uses its default) and a value equal to
the schema's default is only written if the key was already there, so a body never gains keys nobody chose.
"""

import copy
import json
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import quote

from .bodies import JsonObject, JsonValue, dump
from .catalog import Field, Operation

type QueryParams = tuple[tuple[str, str], ...]


class InputError(ValueError):
    """Something typed in the form can't be sent: the message says what and where."""


@dataclass(frozen=True)
class PreparedRequest:
    method: str
    path: str  # from the server's root, with the module prefix and the path parameters filled in
    params: QueryParams
    body: JsonValue = None
    has_body: bool = False


def _scalar(item: Field, value: str) -> JsonValue:
    """One typed value as JSON, checked against the field's kind."""
    match item.kind:
        case "integer":
            try:
                return int(value)
            except ValueError:
                raise InputError(f"{item.name}: «{value}» no es un número entero") from None
        case "number":
            try:
                return float(value)
            except ValueError:
                raise InputError(f"{item.name}: «{value}» no es un número") from None
        case "boolean":
            if value not in ("true", "false"):
                raise InputError(f"{item.name}: «{value}» no es true ni false")
            return value == "true"
        case "choice":
            if value not in item.choices:
                raise InputError(f"{item.name}: «{value}» no es ninguno de {', '.join(item.choices)}")
            return value
        case "json":
            try:
                parsed: JsonValue = json.loads(value)
            except json.JSONDecodeError as error:
                raise InputError(f"{item.name}: JSON inválido ({error.msg}, columna {error.colno})") from None
            return parsed
    return value


def _parts(item: Field, typed: str) -> list[str]:
    parts = [part.strip() for part in typed.split(",")] if item.repeated else [typed.strip()]
    return [part for part in parts if part]


def _text(value: JsonValue) -> str:
    """How a body value is shown in its field."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False)


def _get(body: JsonObject, key: tuple[str, ...]) -> tuple[bool, JsonValue]:
    current: JsonValue = body
    for part in key:
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current


def _set(body: JsonObject, key: tuple[str, ...], value: JsonValue) -> None:
    current = body
    for part in key[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[key[-1]] = value


def _remove(body: JsonObject, key: tuple[str, ...]) -> None:
    """Removes the key, and the objects it leaves empty."""
    parents: list[JsonObject] = [body]
    for part in key[:-1]:
        child = parents[-1].get(part)
        if not isinstance(child, dict):
            return
        parents.append(child)
    parents[-1].pop(key[-1], None)
    for depth in range(len(parents) - 1, 0, -1):
        if parents[depth]:
            break
        parents[depth - 1].pop(key[depth - 1], None)


def body_values(operation: Operation, body: JsonObject) -> dict[str, str]:
    """The body fields' values as the form shows them (lists joined by commas); a key not in the body: its default."""
    values: dict[str, str] = {}
    for item in operation.fields:
        if item.location != "body":
            continue
        found, value = _get(body, item.key)
        if not found:
            values[item.name] = item.default
        elif item.repeated and isinstance(value, list):
            values[item.name] = ", ".join(_text(part) for part in value)
        else:
            values[item.name] = _text(value)
    return values


def apply_body(operation: Operation, values: Mapping[str, str], body: JsonObject) -> JsonObject:
    """A copy of `body` with the form's body fields written in; InputError with the first wrong value."""
    result = copy.deepcopy(body)
    for item in operation.fields:
        if item.location != "body" or item.name not in values:
            continue
        typed = values[item.name].strip()
        present, _ = _get(result, item.key)
        if not typed:
            if item.required and not present:
                raise InputError(f"{item.name} es obligatorio")
            _remove(result, item.key)
            continue
        if typed == item.default and not present:
            continue
        value = [_scalar(item, part) for part in _parts(item, typed)] if item.repeated else _scalar(item, typed)
        _set(result, item.key, value)
    return result


def parse_body(text: str) -> JsonObject:
    """The JSON editor's text as a body object."""
    try:
        parsed: JsonValue = json.loads(text) if text.strip() else {}
    except json.JSONDecodeError as error:
        raise InputError(f"JSON inválido en la línea {error.lineno}, columna {error.colno}: {error.msg}") from None
    if not isinstance(parsed, dict):
        raise InputError("el cuerpo tiene que ser un objeto JSON: { ... }")
    return parsed


def show_body(body: JsonObject) -> str:
    return dump(body)


def prepare(operation: Operation, typed: Mapping[str, str], body: JsonObject | None = None) -> PreparedRequest:
    """The request for `operation` with the typed values (by field name) over `body`; InputError if not valid."""
    path = operation.module.prefix + operation.path
    params: list[tuple[str, str]] = []
    for item in operation.fields:
        if item.location == "body":
            continue
        values = [_text(_scalar(item, part)) for part in _parts(item, typed.get(item.name, ""))]
        if not values:
            if item.required:
                raise InputError(f"{item.name} es obligatorio")
            continue
        if item.location == "path":
            path = path.replace("{" + item.name + "}", quote(values[0], safe=""))
        else:
            params.extend((item.name, value) for value in values)
    if operation.body is None:
        return PreparedRequest(operation.method, path, tuple(params))
    sent = apply_body(operation, typed, body if body is not None else operation.start_body() or {})
    return PreparedRequest(operation.method, path, tuple(params), sent, has_body=True)
