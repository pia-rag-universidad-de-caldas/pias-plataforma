"""The body a form starts from (feature 062): choosing another pipeline template loads its own example."""

from server.console.bodies import RUN_BODIES, RUN_KEY, switched_body, template


def test_another_template_loads_its_example_and_keeps_the_name() -> None:
    body = switched_body(RUN_KEY, "produccion", "experimentos", "mi corrida")
    assert body is not None and body["name"] == "mi corrida" and body["template"] == "experimentos"
    params = body["params"]
    assert isinstance(params, dict) and set(params) == {"chunkear", "embeber"}


def test_the_same_template_or_an_unknown_one_changes_nothing() -> None:
    assert switched_body(RUN_KEY, "experimentos", "experimentos", "") is None
    assert switched_body(RUN_KEY, "produccion", "mia", "") is None
    assert switched_body(("chunking", "POST", "/runs"), "a", "experimentos", "") is None


def test_a_pipeline_run_starts_from_production() -> None:
    assert template(*RUN_KEY) == RUN_BODIES["produccion"]
