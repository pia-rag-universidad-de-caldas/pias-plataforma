"""Which fields go together (feature 062): an optional field that would break a rule can't be added and says why, and
the form isn't sent while a rule is broken or an exclusive group lacks its required one."""

from collections.abc import Callable

import pytest

from server.console.catalog import Field, Module, Operation
from server.console.field_rules import (
    PENDING_FIELDS,
    PENDING_ROUTES,
    RULES,
    Form,
    Rule,
    matches,
    names,
    short,
)

type Catalog = dict[str, tuple[Operation, ...]]
type Find = Callable[[str, str, str], Operation]


def field_of(operation: Operation, name: str) -> Field:
    return next(f for f in operation.fields if f.name == name)


@pytest.mark.parametrize(("key", "rule"), [(key, rule) for key, rules in RULES.items() for rule in rules])
def test_every_rule_names_fields_of_its_operation(operations: Catalog, key: tuple[str, str, str], rule: Rule) -> None:
    module, method, path = key
    found = [op for op in operations[module] if (op.method, op.path) == (method, path)]
    if not found:
        assert key in PENDING_ROUTES, f"{method} /{module}{path} doesn't exist"
        pytest.skip("a route another part of feature 062 adds")
    for name in names(rule):
        if name in PENDING_FIELDS or name.rsplit(".", 1)[-1] in PENDING_FIELDS:
            continue
        assert any(matches(item, name) for item in found[0].fields), f"{name} isn't a field of {method} {path}"


def test_a_field_with_another_one_of_its_group_is_blocked_and_says_which(find: Find) -> None:
    runs = find("chunking", "POST", "/runs")
    form = Form(runs, {"sha256s": "abc"})
    assert form.lock(field_of(runs, "page")) == "incompatible con `sha256s`"


def test_an_added_but_empty_field_already_blocks_the_other_side(find: Find) -> None:
    runs = find("embeddings", "POST", "/runs")
    assert Form(runs, {}, {"page"}).lock(field_of(runs, "sha256s")) == "incompatible con `page`"


def test_removing_the_field_that_blocks_unblocks(find: Find) -> None:
    runs = find("chunking", "POST", "/runs")
    assert Form(runs, {"sha256s": ""}).lock(field_of(runs, "page")) == ""


def test_an_exclusive_group_names_its_options_and_the_one_taken(find: Find) -> None:
    experiments = find("chunking", "POST", "/experiments")
    reason = Form(experiments, {"all": "true"}).lock(field_of(experiments, "sha256s"))
    assert reason == "elige uno de: sha256s, from_experiment, all (ya está `all`)"


def test_a_field_that_only_works_with_another_is_blocked_until_it_is_there(find: Find) -> None:
    files = find("ingesta", "GET", "/data")
    assert Form(files, {}).lock(field_of(files, "month")) == "solo funciona junto con `year`"
    assert Form(files, {"year": "2024"}).lock(field_of(files, "month")) == ""


def test_a_field_that_needs_a_value_of_another_says_which(find: Find) -> None:
    run = find("pipeline", "POST", "/runs")
    reason = Form(run, {"template": "laboratorio"}).lock(field_of(run, "scope"))
    assert reason == "solo funciona con `template` = produccion"


def test_the_default_value_counts_for_a_condition(find: Find) -> None:
    run = find("pipeline", "POST", "/runs")  # template left empty: produccion
    assert Form(run, {}).lock(field_of(run, "part_size")) == ""


def test_per_page_cant_go_alone(find: Find) -> None:
    run = find("pipeline", "POST", "/runs")
    reason = Form(run, {"template": "experimentos"}).lock(field_of(run, "files.per_page"))
    assert reason == "no puede ir solo: necesita `files.pages`"


def test_the_filters_of_a_selection_dont_go_with_a_list(find: Find) -> None:
    run = find("pipeline", "POST", "/runs")
    form = Form(run, {"template": "experimentos", "files.sha256s": "a, b"})
    assert form.lock(field_of(run, "files.year")) == "incompatible con `files.sha256s`"


def test_hybrid_sizes_are_blocked_with_another_chunker(find: Find) -> None:
    config = find("chunking", "PATCH", "/config")
    assert Form(config, {"chunker": "page"}).lock(field_of(config, "max_tokens")) == "incompatible con `chunker = page`"
    assert Form(config, {"chunker": "hybrid"}).lock(field_of(config, "max_tokens")) == ""


def test_a_missing_required_one_of_a_group_stops_sending(find: Find) -> None:
    experiments = find("chunking", "POST", "/experiments")
    assert Form(experiments, {"name": "x", "all": "false"}).problem() == "falta uno de: sha256s, from_experiment, all"


def test_two_of_an_exclusive_group_stop_sending_and_are_flagged(find: Find) -> None:
    ask = find("consultas", "POST", "/ask")
    form = Form(ask, {"against.embeddings_model": "m", "against.embeddings_experiment": "e"})
    assert form.problem() == (
        "`against.embeddings_experiment` y `against.embeddings_model` no van juntos: elige uno de: "
        "embeddings_experiment, embeddings_model"
    )
    assert form.flagged() == {"against.embeddings_model", "against.embeddings_experiment"}


def test_a_field_set_without_what_it_needs_stops_sending(find: Find) -> None:
    run = find("pipeline", "POST", "/runs")
    values = {
        "template": "experimentos",
        "files.pages.from": "1",
        "files.pages.to": "2",
        "params.chunkear.official": "true",
    }
    assert Form(run, values).problem() == "`files.pages` no puede ir solo: necesita `files.per_page`"


def test_the_experiments_template_needs_a_way_to_chunk(find: Find) -> None:
    run = find("pipeline", "POST", "/runs")
    assert Form(run, {"template": "experimentos", "files.all": "true"}).problem() == (
        "falta uno de: experiment, extend, official"
    )


def test_the_experiments_template_without_files_takes_every_parsed_document(find: Find) -> None:
    run = find("pipeline", "POST", "/runs")
    assert Form(run, {"template": "experimentos", "params.chunkear.extend": "e1"}).problem() == ""


def test_production_needs_a_mode_only_when_it_has_files(find: Find) -> None:
    run = find("pipeline", "POST", "/runs")
    assert Form(run, {}).problem() == ""
    assert Form(run, {"files.year": "2024"}).problem().startswith("falta uno de: all")


def test_a_conflict_of_values_loaded_from_the_json_is_flagged(find: Find) -> None:
    runs = find("chunking", "POST", "/runs")
    form = Form(runs, {"sha256s": "a", "per_page": "5"})
    assert form.flagged() == {"sha256s", "per_page"}
    assert form.problem() == "`sha256s` es incompatible con `per_page`"


def test_locks_lists_only_the_blocked_ones(find: Find) -> None:
    runs = find("chunking", "POST", "/runs")
    assert Form(runs, {"sha256s": "a"}).locks(runs.fields) == {
        "page": "incompatible con `sha256s`",
        "per_page": "incompatible con `sha256s`",
    }


def test_an_operation_without_rules_never_blocks() -> None:
    operation = Operation(Module("llm", "/llm"), "POST", "/chat", "", "", (Field("model", "body", "text"),), {})
    assert Form(operation, {"model": "x"}).problem() == "" and Form(operation, {}).lock(operation.fields[0]) == ""


def test_short_names_drop_their_common_parent() -> None:
    assert short(("files.all", "files.sample")) == "all, sample"
    assert short(("a.x", "b.y")) == "a.x, b.y"
