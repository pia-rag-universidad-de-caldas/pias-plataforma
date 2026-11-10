"""The console's menus come from each module's openapi.json (features 034 and 035): fields of the path, the query and
the body (flattened), grouped by resource with their Spanish names."""

from collections.abc import Callable

import pytest

from server.console import texts
from server.console.catalog import MODULES, Operation
from server.console.resources import EXPERIMENTS, HEALTH, group, main_resources

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


@pytest.mark.parametrize(
    ("name", "kind"), [("simulate", "boolean"), ("sha256s", "text"), ("chunking.max_tokens", "integer")]
)
def test_the_keys_of_a_body_are_fields_of_their_type(find: Find, name: str, kind: str) -> None:
    field = next(f for f in find("chunking", "POST", "/experiments").fields if f.name == name)
    assert (field.kind, field.location) == (kind, "body")


def test_a_list_in_a_body_is_a_repeated_field(find: Find) -> None:
    assert next(f for f in find("chunking", "POST", "/runs").fields if f.name == "sha256s").repeated


def test_an_enum_in_a_body_gives_its_choices(find: Find) -> None:
    field = next(f for f in find("chunking", "PUT", "/config").fields if f.name == "chunker")
    assert field.choices == ("hybrid", "hierarchical", "page")


def test_nested_objects_are_flattened(find: Find) -> None:
    names = {f.name for f in find("chunking", "POST", "/experiments").fields}
    assert {"chunking.chunker", "chunking.tokenizer", "chunking.merge_peers", "from_experiment"} <= names
    assert not any(name.startswith(("plan", "conversion", "files")) for name in names)


def test_a_free_object_is_one_json_field(find: Find) -> None:
    fields = {f.name: f for f in find("data", "POST", "/nodes/{label}").fields}
    assert fields["properties"].kind == "json"


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
    assert data == ["health", "schema", "nodes", "relationships", "batch", "progress", "vectors"]


def test_effect_says_whether_it_writes(operations: Catalog, find: Find) -> None:
    reading = texts.action("ingesta", "GET", "/stats/summary", "", "")
    deleting = texts.action("chunking", "DELETE", "/experiments/{id}", "", "")
    assert texts.READS in reading.description and "borra" in deleting.description
    unknown = texts.action("data", "POST", "/new", "New Thing", "Does it.")
    assert unknown.name == "new thing" and "Does it." in unknown.description


def test_experiments_come_first_and_health_has_no_card(operations: Catalog, find: Find) -> None:
    resources = group(operations["chunking"])
    shown = [r.segment for r in main_resources(resources)]
    assert shown[0] == EXPERIMENTS and HEALTH not in shown
    assert set(shown) == {"experiments", "config", "runs", "processes"}


def test_a_nested_key_is_required_only_if_its_object_is_too(operations: Catalog, find: Find) -> None:
    relationship = {f.name: f for f in find("data", "POST", "/relationships").fields}
    assert all(relationship[name].required for name in ("source.label", "source.id", "target.label", "target.id"))
    assert not relationship["properties"].required
    experiment = {f.name: f for f in find("chunking", "POST", "/experiments").fields}
    assert not experiment["chunking.max_tokens"].required  # `chunking` is optional
