"""The free objects of POST /pipeline/runs shown key by key (feature 062): the form fills `files` and `params` like any
flattened body, and keeps what it doesn't offer."""

from collections.abc import Callable

from server.console.bodies import JsonObject
from server.console.catalog import Field, Module, Operation
from server.console.expansions import expand
from server.console.requests import apply_body, body_values

type Find = Callable[[str, str, str], Operation]


def test_files_and_params_of_a_pipeline_run_come_key_by_key(find: Find) -> None:
    names = {f.name for f in find("pipeline", "POST", "/runs").fields}
    assert {"files.sample", "files.pages.from", "params.chunkear.extend", "params.embeber.models"} <= names
    assert "files" not in names and "params" not in names


def test_a_body_with_an_experiment_reads_into_its_fields_and_back(find: Find) -> None:
    run = find("pipeline", "POST", "/runs")
    body: JsonObject = {
        "template": "experimentos",
        "files": {"sample": 5},
        "params": {"embeber": {"models": ["a", "b"]}},
    }
    values = body_values(run, body)
    assert values["files.sample"] == "5" and values["params.embeber.models"] == "a, b"
    assert apply_body(run, {**values, "params.chunkear.extend": "e1"}, body)["params"] == {
        "embeber": {"models": ["a", "b"]},
        "chunkear": {"extend": "e1"},
    }


def test_keys_the_form_doesnt_offer_are_kept(find: Find) -> None:
    run = find("pipeline", "POST", "/runs")
    body: JsonObject = {"params": {"otra": {"x": 1}}}
    assert apply_body(run, body_values(run, body), body)["params"] == {"otra": {"x": 1}}


def test_a_field_a_module_already_types_is_not_expanded() -> None:
    typed = Operation(Module("pipeline", "/pipeline"), "POST", "/runs", "", "", (Field("files", "body", "text"),), {})
    assert expand(typed) is typed
