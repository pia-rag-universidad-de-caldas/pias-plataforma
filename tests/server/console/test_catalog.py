"""The console's menus come from each module's openapi.json (features 034 and 035): fields of the path, the query and
the body (flattened), grouped by resource with their Spanish names."""

from collections.abc import Callable

from server.console import texts
from server.console.catalog import MODULES, Operation
from server.console.resources import group

type Catalog = dict[str, tuple[Operation, ...]]
type Find = Callable[[str, str, str], Operation]


def test_query_fields_keep_types_defaults_and_repetition(operations: Catalog, find: Find) -> None:
    fields = {f.name: f for f in find("ingesta", "GET", "/data").fields}
    assert fields["type"].repeated and fields["type"].kind == "text"
    assert fields["month"].kind == "integer" and not fields["month"].required
    assert fields["page"].default == "1"
    assert fields["week"].description == "as the folder: Semana_04"


def test_enums_become_choices_and_path_fields_are_required(operations: Catalog, find: Find) -> None:
    (kind,) = find("ingesta", "GET", "/source").fields
    assert (kind.kind, kind.choices, kind.default) == ("choice", ("folder", "sql"), "folder")
    label = find("data", "GET", "/nodes/{label}").fields[0]
    assert label.location == "path" and label.required and "PIAA" in label.choices


def test_body_keys_are_fields_with_nested_objects_flattened(operations: Catalog, find: Find) -> None:
    run = {f.name: f for f in find("chunking", "POST", "/runs").fields}
    assert run["simulate"].kind == "boolean" and run["simulate"].location == "body"
    assert run["types"].repeated and run["types"].kind == "text"
    assert run["parameters.max_tokens"].kind == "integer"
    assert run["parameters.table_mode"].choices == ("accurate", "fast")
    experiment = {f.name for f in find("chunking", "POST", "/experiments").fields}
    assert {"files.pages.from", "files.from_experiment", "conversion.include.tables"} <= experiment
    node = {f.name: f for f in find("data", "POST", "/nodes/{label}").fields}
    assert node["properties"].kind == "json"  # a free object: one JSON field


def test_every_operation_is_in_one_resource_with_a_spanish_name(operations: Catalog, find: Find) -> None:
    for each in MODULES:
        resources = group(operations[each.name])
        assert sum(len(r.actions) for r in resources) == len(operations[each.name])
        assert all(texts.RESOURCES.get((each.name, r.segment)) for r in resources), each.name
        for resource in resources:
            for action in resource.actions:
                curated = (each.name, action.operation.method, action.operation.path)
                assert curated in texts.ACTIONS, curated
    data = [r.segment for r in group(operations["data"])]
    assert data == ["health", "schema", "nodes", "relationships", "batch"]


def test_effect_says_whether_it_writes(operations: Catalog, find: Find) -> None:
    reading = texts.action("ingesta", "GET", "/stats/summary", "", "")
    deleting = texts.action("chunking", "DELETE", "/experiments/{id}", "", "")
    assert texts.READS in reading.description and "borra" in deleting.description
    unknown = texts.action("data", "POST", "/new", "New Thing", "Does it.")
    assert unknown.name == "new thing" and "Does it." in unknown.description
