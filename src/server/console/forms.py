"""What a form shows (feature 035): the required fields always; an optional one only when it was added or has a value
of its own (not empty, not its default); the rest stay out of the screen and out of the request. Also the free
objects edited key by key (a node's `properties`, a score's `criteria`) and the guides of an action (feature 037)."""

import json
from collections.abc import Collection, Mapping
from dataclasses import dataclass

from .bodies import JsonObject, JsonValue
from .catalog import Field, Operation

OBJECT_FIELDS = frozenset({"properties", "criteria"})  # free objects edited key by key

PROPERTY_SYNTAX = """Cada propiedad es una clave y un valor. La clave va en español y sin tildes (creditos, nombre).
Cómo escribir el valor:
  texto     Cálculo I               sin comillas
  número    3      4.5
  sí/no     true   false
  lista     [1, 2]    ["a", "b"]    entre corchetes y de un solo tipo
  código    "120501"                un texto que parece número va entre comillas"""

_PROPERTY_EFFECTS = {
    "POST": "Al crear se guardan las que pongas aquí.",
    "PUT": "Al reemplazar quedan SOLO las que pongas aquí: las demás se borran.",
    "PATCH": "Al modificar cambian solo las que pongas aquí; con el valor null esa propiedad se borra.",
}

CRITERIA_SYNTAX = """Cada criterio es un nombre y un número entre 0 y 5 (coherencia = 4, tamano = 2.5). Los de prueba \
son coherencia, completitud y tamano; se puede escribir cualquier otro. Al modificar, un criterio en null se borra."""


BATCH_EXAMPLE: JsonObject = {
    "nodes": [
        {"label": "PIAA", "id": "test-lote-piaa", "mode": "ensure"},
        {"label": "JSON", "id": "test-lote-json", "properties": {"nombre": "programa.pdf", "anio": 2024}},
        {"label": "SECCION", "id": "test-lote-json:s0", "properties": {"orden": 0, "encabezados": ["Objetivos"]}},
    ],
    "relationships": [
        {"type": "ES", "source": {"label": "PIAA", "id": "test-lote-piaa"},
         "target": {"label": "JSON", "id": "test-lote-json"}},
        {"type": "TIENE_SECCION", "source": {"label": "JSON", "id": "test-lote-json"},
         "target": {"label": "SECCION", "id": "test-lote-json:s0"}},
    ],
    "replace_from": {"label": "JSON", "id": "test-lote-json"},
}  # fmt: skip

BATCH_HELP = f"""QUÉ ES
Escribe de una vez un documento y todo lo que cuelga de él: varios nodos y relaciones en una sola transacción. O \
entra todo o no entra nada: si algo falla, el grafo queda como estaba.

CÓMO SE LLENA
Lo más cómodo es F5 (editar JSON): nodes y relationships son listas, y en el formulario van en una sola línea. \
Pega el ejemplo de abajo y cámbialo. Enviar pide confirmación, porque escribe en el grafo.

nodes: los nodos a escribir.
  label       la etiqueta (PIAA, JSON, SECCION...). Las admitidas salen en esquema.
  id          su identificador, único por etiqueta. No puede estar vacío ni repetirse en el lote.
  properties  sus datos, clave = valor (opcional).
  mode        qué hacer si el nodo ya existe (opcional; por defecto replace):
    replace   deja SOLO las propiedades enviadas; las demás se borran.
    merge     pone las enviadas y conserva las demás.
    ensure    no toca el que ya existe; solo lo crea si falta.

relationships: las relaciones a escribir.
  type            el tipo (ES, TIENE_SECCION...). El esquema debe admitirlo entre esas dos etiquetas.
  source, target  los extremos, cada uno con label e id. Deben venir en nodes o existir ya en el grafo.
  properties      sus datos (opcional). Si la relación ya existe, sus propiedades se reemplazan.

replace_from: un nodo cuyo contenido se reemplaza (opcional).
  Antes de escribir borra lo que cuelga de él por relaciones de composición (TIENE_SECCION, TIENE_FRAGMENTO, \
TIENE...).
  No borra el nodo, ni lo que está arriba de él, ni lo compartido. Sirve para reprocesar sin dejar secciones viejas.
  Cuidado: TIENE es de composición, así que también borra los HALLAZGOS que cuelguen de ese nodo.

QUÉ PUEDE FALLAR
422, sin escribir nada: etiqueta o tipo que no existen, un id vacío, un nodo o relación repetidos, una relación \
que el esquema no admite o un extremo que no está. 503: Neo4j no responde.

QUÉ RESPONDE
deleted (borrados por replace_from), created (nuevos), replaced, merged y kept (los que ya existían, según su \
mode) y relationships (relaciones escritas). Cada nodo enviado cuenta en uno solo de created, replaced, merged o kept.

EJEMPLO
Un PIAA con su JSON y una sección; se puede enviar varias veces y deja lo mismo.

{json.dumps(BATCH_EXAMPLE, indent=2, ensure_ascii=False)}"""

GUIDES: dict[tuple[str, str, str], str] = {("data", "POST", "/batch"): BATCH_HELP}


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


def value_kind(value: JsonValue) -> str:
    """How a property's value is stored, in words."""
    if value is None:
        return "nulo: se borra"
    if isinstance(value, bool):
        return "sí/no"
    if isinstance(value, int | float):
        return "número"
    if isinstance(value, list):
        return "lista"
    return "objeto: Neo4j no lo guarda" if isinstance(value, dict) else "texto"


def _is_criterion(item: Field) -> bool:
    return item.key[-1] == "criteria"


def object_guide(item: Field, method: str) -> str:
    """The syntax of a free object's values and what the action does with them (feature 038)."""
    if _is_criterion(item):
        return CRITERIA_SYNTAX
    return f"{PROPERTY_SYNTAX}\n{_PROPERTY_EFFECTS.get(method, '')}".rstrip()


def _list_kind(value: JsonValue) -> str:
    return "número" if isinstance(value, int | float) and not isinstance(value, bool) else type(value).__name__


def value_problem(item: Field, value: JsonValue) -> str | None:
    """Why the API would reject this value of a free object; None if it wouldn't."""
    if value is None:
        return None
    if _is_criterion(item):
        is_number = isinstance(value, int | float) and not isinstance(value, bool)
        return None if is_number else "un criterio es un número entre 0 y 5"
    if isinstance(value, dict):
        return "Neo4j no guarda objetos: usa texto, número, sí/no o una lista"
    if isinstance(value, list):
        kinds = {_list_kind(v) for v in value}
        if not kinds <= {"número", "str", "bool"}:
            return "una lista solo lleva textos, números o sí/no"
        if len(kinds) > 1:
            return "una lista lleva valores de un solo tipo"
    return None


def preview(item: Field, text: str) -> str:
    """What the modal says while the value is typed: how it will be stored, or why it can't."""
    value = parse_value(text)
    problem = value_problem(item, value)
    return f"✗ {problem}" if problem else f"Se guardará como: {value_kind(value)}"


def show_value(value: JsonValue) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def compact(value: JsonObject) -> str:
    return json.dumps(value, ensure_ascii=False) if value else ""
