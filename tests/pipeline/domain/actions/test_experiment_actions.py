"""The stages of the experiments pipeline (feature 062) over fake ports: what each asks of data, chunking and
embeddings (only ids) and what it leaves for the next one."""

import pytest
from pipeline_fakes import ExperimentsModules

from pipeline.domain import CATALOG
from pipeline.domain.actions.experiments import seeded
from pipeline.models import (
    CHUNKING_EXPERIMENT,
    EMBEDDED,
    EMBEDDINGS_EXPERIMENTS,
    FILE_BATCH,
    ActionContext,
    ActionError,
    ActionOutput,
    ChunkingExperimentInfo,
    EmbeddingsExperimentInfo,
    ExperimentState,
    JsonObject,
    PipelineRun,
    RunStatus,
    RunStore,
    Selection,
    Stage,
    Template,
)

FIT: JsonObject = {"chunker": "hybrid", "fit": [{"tokenizer": "minilm", "max_tokens": 126}]}


class Store(RunStore):
    def __init__(self, other: PipelineRun | None = None) -> None:
        self.other = other

    def templates(self) -> list[Template]:
        return []

    def template(self, id: str) -> Template | None:
        return None

    def save_template(self, template: Template) -> None: ...

    def delete_template(self, id: str) -> bool:
        return False

    def runs(self) -> list[PipelineRun]:
        return []

    def run(self, id: str) -> PipelineRun | None:
        return self.other if self.other is not None and self.other.id == id else None

    def save_run(self, run: PipelineRun, created: bool = False) -> None: ...


def run_action(
    fakes: ExperimentsModules,
    action: str,
    artifacts: JsonObject | None = None,
    config: JsonObject | None = None,
    files: Selection | None = None,
    store: RunStore | None = None,
) -> ActionOutput:
    stage = Stage("s", action)
    run = PipelineRun("r1", "prueba", Template("t", "t", "", (stage,)), RunStatus.RUNNING, "now", files)
    context = ActionContext(run, stage, config or {}, artifacts or {}, fakes.modules, store or Store())
    return CATALOG[action].run(context)


@pytest.fixture
def fakes() -> ExperimentsModules:
    return ExperimentsModules()


def test_the_selection_reads_every_page_of_what_data_answers(fakes: ExperimentsModules) -> None:
    fakes.data.parsed = [f"p{i:03}" for i in range(1200)]
    output = run_action(fakes, "data.parsed")
    assert output.artifacts[FILE_BATCH] == fakes.data.parsed
    assert [a[3] for a in fakes.data.asked] == [1, 2, 3] and fakes.data.asked[0][1] == {"all": True}


def test_official_selects_the_chunked_and_extend_leaves_out_what_the_experiment_has(fakes: ExperimentsModules) -> None:
    assert run_action(fakes, "data.parsed", config={"universe": "chunked"}).artifacts[FILE_BATCH] == ["p0", "p1", "p2"]
    fakes.data.had["c9"] = {"p0", "p1", "p2", "p3", "p4"}
    output = run_action(fakes, "data.parsed", config={"exclude_experiment": "c9"})
    assert output.artifacts == {FILE_BATCH: []}


def test_an_empty_selection_without_extend_fails(fakes: ExperimentsModules) -> None:
    with pytest.raises(ActionError, match="no documents"):
        run_action(fakes, "data.parsed", files=Selection(sha256s=("zz",)))


def test_from_run_takes_that_runs_batch(fakes: ExperimentsModules) -> None:
    other = PipelineRun("r0", "o", Template("t", "t", "", ()), RunStatus.DONE, "now", artifacts={FILE_BATCH: ["p1"]})
    output = run_action(fakes, "data.parsed", files=Selection(from_run="r0"), store=Store(other))
    assert output.artifacts == {FILE_BATCH: ["p1"]} and fakes.data.asked[0][1] == {"sha256s": ["p1"]}


def test_a_new_experiment_chunks_the_batch_with_a_fit_for_every_model(fakes: ExperimentsModules) -> None:
    config: JsonObject = {"experiment": {"name": "n", "chunking": {"max_tokens": 200}}, "models": ["minilm", "e5"]}
    output = run_action(fakes, "chunking.extend", {FILE_BATCH: ["p0", "p1"]}, config)
    body = fakes.chunking.started[0]
    assert (body["name"], body["sha256s"]) == ("n", ["p0", "p1"])
    assert body["chunking"] == {
        "chunker": "hybrid",
        "fit": [{"tokenizer": "minilm", "max_tokens": 126}, {"tokenizer": "e5", "max_tokens": 200}],
    }
    assert output.artifacts == {CHUNKING_EXPERIMENT: "c1"}


def test_extend_adds_only_the_new_ones_and_with_none_chunks_nothing(fakes: ExperimentsModules) -> None:
    fakes.chunking.experiments["c9"] = ChunkingExperimentInfo("c9", "finished", FIT)
    output = run_action(fakes, "chunking.extend", {FILE_BATCH: ["p3"]}, {"extend": "c9"})
    assert fakes.chunking.added == [("c9", ["p3"])] and output.artifacts == {CHUNKING_EXPERIMENT: "c9"}
    run_action(fakes, "chunking.extend", {FILE_BATCH: []}, {"extend": "c9"})
    assert len(fakes.chunking.added) == 1


def test_extending_a_running_experiment_fails(fakes: ExperimentsModules) -> None:
    fakes.chunking.experiments["c9"] = ChunkingExperimentInfo("c9", "running", FIT)
    with pytest.raises(ActionError, match="is running"):
        run_action(fakes, "chunking.extend", {FILE_BATCH: ["p3"]}, {"extend": "c9"})


def test_official_doesnt_chunk(fakes: ExperimentsModules) -> None:
    output = run_action(fakes, "chunking.extend", {FILE_BATCH: ["p0"]}, {"official": True})
    assert output.artifacts == {CHUNKING_EXPERIMENT: None} and fakes.chunking.started == []


@pytest.mark.parametrize(("status", "resumed"), [("failed", ["c9"]), ("interrupted", ["c9"]), ("finished", [])])
def test_resumed_it_resumes_the_experiment_it_started_if_it_stopped(
    fakes: ExperimentsModules, status: str, resumed: list[str]
) -> None:
    fakes.chunking.experiments["c9"] = ChunkingExperimentInfo("c9", status, FIT)
    config: JsonObject = {"experiment": {"chunking": {}}}
    run_action(fakes, "chunking.extend", {FILE_BATCH: ["p0"], CHUNKING_EXPERIMENT: "c9"}, config)
    assert fakes.chunking.resumed == resumed and fakes.chunking.started == []


@pytest.mark.parametrize("status", ["finished", "partial"])
def test_the_wait_goes_on_when_data_says_the_experiment_ended(fakes: ExperimentsModules, status: str) -> None:
    fakes.data.states["c1"] = ExperimentState("c1", status)
    assert run_action(fakes, "data.wait_experiment", {CHUNKING_EXPERIMENT: "c1"}).result == {
        "experiment": "c1",
        "status": status,
    }


def test_the_wait_stops_the_run_when_the_experiment_failed(fakes: ExperimentsModules) -> None:
    fakes.data.states["c1"] = ExperimentState("c1", "failed", "data went down")
    with pytest.raises(ActionError, match="ended failed: data went down"):
        run_action(fakes, "data.wait_experiment", {CHUNKING_EXPERIMENT: "c1"})


def test_the_wait_has_nothing_to_wait_for_with_official(fakes: ExperimentsModules) -> None:
    assert run_action(fakes, "data.wait_experiment", {CHUNKING_EXPERIMENT: None}).artifacts == {}


def test_embedding_creates_one_experiment_per_model_or_continues_the_one_it_has(fakes: ExperimentsModules) -> None:
    fakes.chunking.experiments["c1"] = ChunkingExperimentInfo(
        "c1", "finished", {"fit": [{"tokenizer": "minilm", "max_tokens": 126}, {"tokenizer": "e5", "max_tokens": 300}]}
    )
    fakes.embeddings.existing = [EmbeddingsExperimentInfo("e0", "minilm", "finished", 2)]
    output = run_action(fakes, "embeddings.experiments", {CHUNKING_EXPERIMENT: "c1"}, {"models": ["minilm", "e5"]})
    assert fakes.embeddings.resumed == ["e0"]
    created = fakes.embeddings.created[0]
    assert (created["chunking_experiment"], created["model"], created["max_tokens"]) == ("c1", "e5", 305)
    assert output.artifacts == {EMBEDDINGS_EXPERIMENTS: ["e0", "e1"], EMBEDDED: []}


def test_a_model_that_fails_doesnt_stop_the_others_and_fails_the_stage_after_them(fakes: ExperimentsModules) -> None:
    fakes.chunking.experiments["c1"] = ChunkingExperimentInfo("c1", "finished", FIT)
    fakes.embeddings.failing = {"minilm"}
    with pytest.raises(ActionError, match=r"minilm: e1 ended failed: boom .*resume the run"):
        run_action(fakes, "embeddings.experiments", {CHUNKING_EXPERIMENT: "c1"}, {"models": ["minilm", "e5"]})
    assert [b["model"] for b in fakes.embeddings.created] == ["minilm", "e5"]


def test_without_models_nothing_is_embedded(fakes: ExperimentsModules) -> None:
    output = run_action(fakes, "embeddings.experiments", {CHUNKING_EXPERIMENT: "c1"})
    assert output.artifacts == {EMBEDDINGS_EXPERIMENTS: [], EMBEDDED: []}


def test_official_embeds_the_batch_with_each_model_next_to_the_active(fakes: ExperimentsModules) -> None:
    artifacts: JsonObject = {CHUNKING_EXPERIMENT: None, FILE_BATCH: ["p0", "p1"]}
    output = run_action(fakes, "embeddings.experiments", artifacts, {"models": ["e5", "bge"]})
    assert fakes.embeddings.runs == [(["p0", "p1"], "e5"), (["p0", "p1"], "bge")]
    assert output.artifacts == {EMBEDDINGS_EXPERIMENTS: [], EMBEDDED: ["p0", "p1"]}


def test_embed_models_alone_gives_the_embedded(fakes: ExperimentsModules) -> None:
    output = run_action(fakes, "embeddings.embed_models", {FILE_BATCH: ["p0"]}, {"models": ["e5"]})
    assert output.artifacts == {EMBEDDED: ["p0"]}
    fakes.embeddings.failing = {"e5"}
    with pytest.raises(ActionError, match="e5: the run r2 ended failed"):
        run_action(fakes, "embeddings.embed_models", {FILE_BATCH: ["p0"]}, {"models": ["e5"]})


def test_a_sample_without_a_seed_gets_one_drawn_once() -> None:
    assert seeded({"sample": 300}, draw=lambda: 7) == {"sample": 300, "seed": 7}


@pytest.mark.parametrize("files", [{"sample": 300, "seed": 3}, {"all": True}, {"pages": {"from": 1, "to": 2}}])
def test_a_seeded_sample_or_another_mode_is_left_as_asked(files: JsonObject) -> None:
    assert seeded(files, draw=lambda: 7) == files
