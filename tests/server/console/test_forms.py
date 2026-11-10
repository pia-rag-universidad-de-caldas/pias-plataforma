"""What a form shows (feature 035): required fields always, optional ones only when added or with a value of
their own; and the values of a property as typed."""

import json
from collections.abc import Callable
from dataclasses import fields

import pytest
from pydantic import TypeAdapter

from data.api.schemas import Batch
from data.models import BatchNode, BatchResult, NodeMode, Relationship
from data.schema import batch_problems
from server.console.catalog import Field, Module, Operation
from server.console.forms import (
    BATCH_EXAMPLE,
    BATCH_HELP,
    GUIDES,
    is_object,
    object_guide,
    object_of,
    parse_value,
    preview,
    show_value,
    value_kind,
    value_problem,
    visible,
)

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


def test_a_free_object_is_edited_key_by_key(find: Find) -> None:
    node = find("data", "POST", "/nodes/{label}")
    assert is_object(next(f for f in node.fields if f.name == "properties"))


@pytest.mark.parametrize(("text", "expected"), [('{"nombre": "x"}', {"nombre": "x"}), ("[1]", {}), ("", {})])
def test_object_of_only_reads_objects(text: str, expected: dict[str, str]) -> None:
    assert object_of(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"), [("3", 3), ("Cálculo I", "Cálculo I"), ("null", None), ('["a", "b"]', ["a", "b"])]
)
def test_parse_value_reads_a_value_as_typed(text: str, expected: object) -> None:
    assert parse_value(text) == expected


@pytest.mark.parametrize(("value", "expected"), [("texto", "texto"), (True, "true")])
def test_show_value_writes_a_value_as_it_is_typed(value: str | bool, expected: str) -> None:
    assert show_value(value) == expected


def test_a_value_says_how_it_is_stored() -> None:
    assert value_kind(parse_value("3")) == "número"
    assert value_kind(parse_value("true")) == "sí/no"
    assert value_kind(parse_value("[1, 2]")) == "lista"
    assert value_kind(parse_value("Cálculo I")) == "texto"
    assert value_kind(parse_value("null")).startswith("nulo")
    assert "no lo guarda" in value_kind(parse_value('{"a": 1}'))


def test_the_batch_guide_shows_an_example_that_is_a_valid_batch() -> None:
    batch = TypeAdapter(Batch).validate_python(BATCH_EXAMPLE)
    relationships = [Relationship(r.type, r.source, r.target, r.properties) for r in batch.relationships]
    assert batch_problems(batch.nodes, relationships) == []
    assert json.dumps(BATCH_EXAMPLE, indent=2, ensure_ascii=False) in BATCH_HELP
    assert GUIDES[("data", "POST", "/batch")] == BATCH_HELP


def test_the_batch_guide_names_every_key_and_mode_of_the_api() -> None:
    keys = {f.name for f in fields(Batch)} | {f.name for f in fields(BatchNode)} | {f.name for f in fields(BatchResult)}
    modes = {mode.value for mode in NodeMode}
    missing = {word for word in keys | modes if word not in BATCH_HELP}
    assert missing == set()


def _free_object(name: str) -> Field:
    return Field(name, "body", "json")


def test_the_guide_of_properties_shows_the_syntax_and_what_the_action_does() -> None:
    properties = _free_object("properties")
    assert '"120501"' in object_guide(properties, "POST") and "[1, 2]" in object_guide(properties, "POST")
    assert "SOLO" in object_guide(properties, "PUT")
    assert "null" in object_guide(properties, "PATCH")
    assert "entre 0 y 5" in object_guide(_free_object("criteria"), "POST")


def test_what_the_api_would_reject_is_said_before_sending() -> None:
    properties, criteria = _free_object("properties"), _free_object("criteria")
    for text in ("3", "Cálculo I", "true", "[1, 2.5]", '["a"]', "null", '"120501"', "[]"):
        assert value_problem(properties, parse_value(text)) is None, text
    for text in ('{"a": 1}', '[1, "a"]', "[[1]]", '[{"a": 1}]', "[1, true]"):
        assert value_problem(properties, parse_value(text)), text
    assert value_problem(criteria, 4.5) is None and value_problem(criteria, None) is None
    assert value_problem(criteria, "alto") and value_problem(criteria, True)


def test_the_preview_says_how_a_value_will_be_stored() -> None:
    properties = _free_object("properties")
    assert preview(properties, "3") == "Se guardará como: número"
    assert preview(properties, '"120501"') == "Se guardará como: texto"
    assert preview(properties, '{"a": 1}').startswith("✗")
