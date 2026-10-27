"""What a form shows (feature 035): the required fields always; an optional one only when it was added or has a value
of its own (not empty, not its default); the rest stay out of the screen and out of the request. Also the free
objects edited key by key (a node's `properties`, a score's `criteria`)."""

import json
from collections.abc import Collection, Mapping
from dataclasses import dataclass

from .bodies import JsonObject, JsonValue
from .catalog import Field, Operation

OBJECT_FIELDS = frozenset({"properties", "criteria"})  # free objects edited key by key

PROPERTIES_HELP = """Propiedades: los datos guardados en el nodo o en la relación, como pares clave = valor
(nombre = Cálculo I, creditos = 3). Las claves del grafo están en español, sin tildes.
Valores: texto, número (3, 4.5), true/false o una lista de un solo tipo ([1, 2], ["a", "b"]); Neo4j no guarda objetos
dentro de una propiedad. Lo que no es JSON válido se guarda como texto.
Crear (POST) guarda las que pongas. Reemplazar (PUT) deja SOLO las que pongas: las demás se borran. Modificar
(PATCH) cambia solo las que pongas, y una en null se borra.
Al reemplazar o modificar algo que existe, se cargan sus propiedades actuales (GET de la misma ruta)."""

CRITERIA_HELP = """Criterios de la puntuación: nombre = número (entre 0 y 5). Los de prueba son coherencia,
completitud y tamano; se puede agregar cualquier otro sin cambiar código. Al modificar (PATCH), uno en null se borra."""


@dataclass(frozen=True)
class Visible:
    required: list[Field]
    optional: list[Field]  # the optional fields in use, shown under «Opcionales»
    hidden: list[Field]  # the optional fields that can be added


def in_use(item: Field, values: Mapping[str, str], added: Collection[str]) -> bool:
    """An optional field the form shows: added, with a value of its own, or a free object (always: it is the data)."""
    return item.name in added or is_object(item) or values.get(item.name, "").strip() not in ("", item.default)


def visible(operation: Operation, values: Mapping[str, str], added: Collection[str]) -> Visible:
    required = [f for f in operation.fields if f.required]
    optional = [f for f in operation.fields if not f.required]
    shown = [f for f in optional if in_use(f, values, added)]
    return Visible(required, shown, [f for f in optional if f not in shown])


def is_object(item: Field) -> bool:
    return item.kind == "json" and item.key[-1] in OBJECT_FIELDS


def object_of(text: str) -> JsonObject:
    """A free object field's value as a dict ({} if empty or not an object)."""
    try:
        parsed: JsonValue = json.loads(text) if text.strip() else {}
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def parse_value(text: str) -> JsonValue:
    """A property's value as typed: JSON when it is (3, true, null, [1, 2], "x"), otherwise the text itself."""
    try:
        parsed: JsonValue = json.loads(text)
    except json.JSONDecodeError:
        return text
    return parsed


def show_value(value: JsonValue) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def compact(value: JsonObject) -> str:
    return json.dumps(value, ensure_ascii=False) if value else ""
