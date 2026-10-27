"""From a form to the HTTP request (features 034 and 035): what is checked, and the body kept between the form and
the JSON editor."""

import httpx
import pytest

from server.console.catalog import Field, Module, Operation
from server.console.client import reply
from server.console.requests import InputError, apply_body, body_values, parse_body, prepare

OPERATION = Operation(
    module=Module("chunking", "/chunking"),
    method="POST",
    path="/experiments/{id}/runs",
    summary="",
    description="",
    fields=(
        Field("id", "path", "text", required=True),
        Field("type", "query", "text", repeated=True),
        Field("year", "query", "integer"),
        Field("kind", "query", "choice", choices=("folder", "sql")),
        Field("simulate", "body", "boolean", default="false"),
        Field("types", "body", "text", repeated=True),
        Field("parameters.max_tokens", "body", "integer", default="512"),
        Field("properties", "body", "json"),
    ),
    body={"simulate": True, "limit": 3},
)


def test_fills_the_path_escaped_and_repeats_lists() -> None:
    request = prepare(OPERATION, {"id": "a/b c", "type": "pdf, docx,", "year": "2024"})
    assert request.path == "/chunking/experiments/a%2Fb%20c/runs"
    assert request.params == (("type", "pdf"), ("type", "docx"), ("year", "2024"))
    assert request.has_body and request.body == {"simulate": True, "limit": 3}


def test_body_fields_are_written_typed_and_nested() -> None:
    typed = {"id": "e1", "simulate": "false", "types": "pdf,docx", "parameters.max_tokens": "256",
             "properties": '{"nombre": "x"}'}  # fmt: skip
    body = prepare(OPERATION, typed).body
    assert body == {
        "simulate": False,
        "limit": 3,
        "types": ["pdf", "docx"],
        "parameters": {"max_tokens": 256},
        "properties": {"nombre": "x"},
    }


def test_defaults_are_not_added_and_emptied_fields_are_removed() -> None:
    body = apply_body(OPERATION, {"parameters.max_tokens": "512", "simulate": ""}, {"simulate": True, "limit": 3})
    assert body == {"limit": 3}  # 512 is the default and wasn't there; simulate emptied
    nested = apply_body(OPERATION, {"parameters.max_tokens": ""}, {"parameters": {"max_tokens": 9}})
    assert nested == {}  # the object it leaves empty goes too


def test_the_form_reads_the_body_back_after_the_json_editor() -> None:
    body = parse_body('{"types": ["pdf", "doc"], "parameters": {"max_tokens": 100}, "properties": {"a": 1}}')
    values = body_values(OPERATION, body)
    assert values["types"] == "pdf, doc" and values["parameters.max_tokens"] == "100"
    assert values["simulate"] == "false" and values["properties"] == '{"a": 1}'
    assert apply_body(OPERATION, values, body) == body | {}  # unchanged form: same body


@pytest.mark.parametrize(
    ("typed", "problem"),
    [
        ({}, "id es obligatorio"),
        ({"id": "e1", "year": "dos mil"}, "no es un número entero"),
        ({"id": "e1", "kind": "ftp"}, "no es ninguno de folder, sql"),
        ({"id": "e1", "properties": "{x"}, "properties: JSON inválido"),
    ],
)
def test_the_first_problem_is_reported(typed: dict[str, str], problem: str) -> None:
    with pytest.raises(InputError, match=problem):
        prepare(OPERATION, typed)


def test_the_json_editor_only_takes_an_object() -> None:
    with pytest.raises(InputError, match="objeto JSON"):
        parse_body("[1, 2]")
    with pytest.raises(InputError, match="línea 1"):
        parse_body('{"a": }')


def test_replies_keep_the_json_its_id_and_show_binaries_by_size() -> None:
    created = reply(httpx.Response(202, json={"run": {"id": "r1", "status": "queued"}}))
    assert created.ok and created.id == "r1" and created.data == {"run": {"id": "r1", "status": "queued"}}
    refused = reply(httpx.Response(422, json={"detail": "no"}))
    assert not refused.ok and refused.id is None
    pdf = reply(httpx.Response(200, content=b"%PDF" * 10, headers={"content-type": "application/pdf"}))
    assert pdf.text == "(40 bytes de application/pdf)"
