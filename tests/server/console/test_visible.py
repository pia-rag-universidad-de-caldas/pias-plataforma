"""What a form shows (feature 035): required fields always, optional ones only when added or with a value of
their own; and the values of a property as typed."""

from collections.abc import Callable

from server.console.catalog import Field, Module, Operation
from server.console.forms import is_object, object_of, parse_value, show_value, visible

type Find = Callable[[str, str, str], Operation]

OPERATION = Operation(
    Module("chunking", "/chunking"),
    "POST",
    "/runs",
    "",
    "",
    (
        Field("id", "path", "text", required=True),
        Field("simulate", "body", "boolean", default="false"),
        Field("limit", "body", "integer"),
        Field("parameters.max_tokens", "body", "integer", default="512"),
    ),
    {},
)


def test_only_required_fields_and_optional_ones_in_use_are_shown() -> None:
    names = visible(OPERATION, {"simulate": "false", "limit": "", "parameters.max_tokens": "512"}, set())
    assert [f.name for f in names.required] == ["id"] and names.optional == []
    assert [f.name for f in names.hidden] == ["simulate", "limit", "parameters.max_tokens"]
    in_use = visible(OPERATION, {"simulate": "true", "parameters.max_tokens": "256"}, {"limit"})
    assert [f.name for f in in_use.optional] == ["simulate", "limit", "parameters.max_tokens"]


def test_properties_are_edited_key_by_key(find: Find) -> None:
    node = find("data", "POST", "/nodes/{label}")
    assert is_object(next(f for f in node.fields if f.name == "properties"))
    assert object_of('{"nombre": "x"}') == {"nombre": "x"} and object_of("[1]") == {} and object_of("") == {}
    assert parse_value("3") == 3 and parse_value("Cálculo I") == "Cálculo I" and parse_value("null") is None
    assert parse_value('["a", "b"]') == ["a", "b"] and show_value("texto") == "texto" and show_value(True) == "true"
