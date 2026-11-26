"""The experiments pipeline's params and checks (feature 062): the mode of the chunking stage, the models, what each
stage gets of the others, the 422/404/409 before launching and the plan a simulation answers."""

import pytest
from pipeline_fakes import ExperimentsModules

from pipeline.domain import EXPERIMENTS
from pipeline.domain.experiments import check, mode, models, plan, prepared, unpaged
from pipeline.models import (
    ChunkingExperimentInfo,
    ConflictError,
    EmbeddingsExperimentInfo,
    InvalidRequest,
    JsonObject,
    NotFoundError,
)

STAGES = EXPERIMENTS.stages
NEW: JsonObject = {"experiment": {"name": "x", "chunking": {"chunker": "hybrid", "max_tokens": 200}}}


def params(chunkear: JsonObject, names: list[str] | None = None) -> dict[str, JsonObject]:
    found: dict[str, JsonObject] = {"chunkear": chunkear}
    if names is not None:
        found["embeber"] = {"models": [*names]}
    return found


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({}, "exactly one of"),
        ({"experiment": {}, "official": True}, "exactly one of"),
        ({"official": "yes"}, "official must be true"),
        ({"extend": ""}, "id of a chunking experiment"),
        ({"experiment": {"nombre": "x"}}, "unknown keys"),
        ({"experiment": {"chunking": 3}}, "must be an object"),
    ],
)
def test_the_chunking_stage_says_exactly_one_mode(config: JsonObject, message: str) -> None:
    with pytest.raises(InvalidRequest, match=message):
        mode(config)


@pytest.mark.parametrize(("value", "message"), [("minilm", "list of model names"), (["a", "a"], "repeats")])
def test_the_models_are_a_list_without_repeats(value: JsonObject, message: str) -> None:
    with pytest.raises(InvalidRequest, match=message):
        models({"models": value})


def test_without_models_nothing_is_embedded() -> None:
    assert models({}) == []


def test_extend_selects_without_the_experiments_documents_and_chunks_for_the_models() -> None:
    changed = prepared(STAGES, params({"extend": "c9"}, ["minilm"]))
    assert changed["seleccionar"] == {"universe": "parsed", "exclude_experiment": "c9"}
    assert changed["chunkear"]["models"] == ["minilm"]


def test_official_selects_the_officially_chunked() -> None:
    assert prepared(STAGES, params({"official": True}))["seleccionar"] == {"universe": "chunked"}


def test_a_template_without_chunking_extend_keeps_its_params() -> None:
    assert prepared(EXPERIMENTS.stages[:1], {"x": {}}) == {"x": {}}


def test_a_new_experiment_with_served_models_fits() -> None:
    fakes = ExperimentsModules()
    check(STAGES, prepared(STAGES, params(NEW, ["minilm", "e5"])), fakes.modules)


def test_a_model_embeddings_doesnt_serve_is_a_422() -> None:
    fakes = ExperimentsModules()
    with pytest.raises(InvalidRequest, match="aren't served"):
        check(STAGES, prepared(STAGES, params(NEW, ["nope"])), fakes.modules)


def test_a_tokenizer_with_models_is_a_422() -> None:
    fakes = ExperimentsModules()
    chunkear: JsonObject = {"experiment": {"chunking": {"tokenizer": "minilm"}}}
    with pytest.raises(InvalidRequest, match=r"chunking\.tokenizer"):
        check(STAGES, prepared(STAGES, params(chunkear, ["minilm"])), fakes.modules)


def test_extending_an_experiment_that_doesnt_exist_is_a_404_and_a_running_one_a_409() -> None:
    fakes = ExperimentsModules()
    with pytest.raises(NotFoundError):
        check(STAGES, prepared(STAGES, params({"extend": "c9"})), fakes.modules)
    fakes.chunking.experiments["c9"] = ChunkingExperimentInfo("c9", "running", {})
    with pytest.raises(ConflictError, match="running"):
        check(STAGES, prepared(STAGES, params({"extend": "c9"})), fakes.modules)


def test_extending_needs_every_model_covered_by_the_experiments_chunks() -> None:
    fakes = ExperimentsModules()
    fit: JsonObject = {"chunker": "hybrid", "fit": [{"tokenizer": "minilm", "max_tokens": 126}]}
    fakes.chunking.experiments["c9"] = ChunkingExperimentInfo("c9", "finished", fit)
    check(STAGES, prepared(STAGES, params({"extend": "c9"}, ["minilm"])), fakes.modules)
    with pytest.raises(InvalidRequest, match=r"e5 doesn't fit.*a new experiment is needed"):
        check(STAGES, prepared(STAGES, params({"extend": "c9"}, ["minilm", "e5"])), fakes.modules)


def test_official_needs_the_active_configuration_to_fit_each_model() -> None:
    fakes = ExperimentsModules()
    check(STAGES, prepared(STAGES, params({"official": True}, ["minilm"])), fakes.modules)
    with pytest.raises(InvalidRequest, match="the official chunks: bge doesn't fit"):
        check(STAGES, prepared(STAGES, params({"official": True}, ["bge"])), fakes.modules)
    fakes.chunking.active = None
    with pytest.raises(InvalidRequest, match="no active configuration"):
        check(STAGES, prepared(STAGES, params({"official": True}, ["minilm"])), fakes.modules)


def test_the_plan_of_a_new_experiment_creates_one_per_model() -> None:
    fakes = ExperimentsModules()
    found = plan(STAGES, prepared(STAGES, params(NEW, ["minilm", "e5"])), {"all": True}, ["p0"], fakes.modules)
    assert found == {
        "documents": 1,
        "mode": "experiment",
        "models": [{"model": "minilm", "action": "create"}, {"model": "e5", "action": "create"}],
    }


def test_the_plan_of_extend_counts_what_it_had_and_continues_its_models() -> None:
    fakes = ExperimentsModules()
    fakes.data.had["c9"] = {"p0", "p1"}
    fakes.embeddings.existing = [EmbeddingsExperimentInfo("e2", "minilm", "finished", 3)]
    found = plan(
        STAGES, prepared(STAGES, params({"extend": "c9"}, ["minilm", "e5"])), {"all": True}, ["p2"], fakes.modules
    )
    assert found["already"] == 2 and found["experiment"] == "c9"
    assert found["models"] == [
        {"model": "minilm", "action": "continue", "experiment": "e2"},
        {"model": "e5", "action": "create"},
    ]


def test_the_plan_of_official_embeds_each_model() -> None:
    fakes = ExperimentsModules()
    found = plan(STAGES, prepared(STAGES, params({"official": True}, ["e5"])), {"all": True}, [], fakes.modules)
    assert found["models"] == [{"model": "e5", "action": "embed"}]


@pytest.mark.parametrize(
    ("files", "every"),
    [
        ({"sample": 3, "seed": 1, "year": 2024}, {"all": True, "year": 2024}),
        ({"pages": {"from": 1, "to": 2}, "per_page": 5}, {"all": True}),
        ({"sha256s": ["a"]}, {"sha256s": ["a"]}),
    ],
)
def test_already_counts_over_every_document_the_filters_take(files: JsonObject, every: JsonObject) -> None:
    assert unpaged(files) == every
