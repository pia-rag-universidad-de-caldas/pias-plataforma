"""The experiments pipeline end to end (feature 062) through POST /pipeline/runs and the executor, over fake ports:
select in data → chunk in an experiment → data says it ended → embed with each model; simulate, the 422 before
launching and resuming a run whose chunking experiment failed."""

import time

import pytest
from fastapi import Response
from pipeline_fakes import ExperimentsModules, MemoryStore

from pipeline.api.actor_registry import ActorRegistry
from pipeline.api.executor import Executor
from pipeline.api.routes.runs import start_run
from pipeline.api.schemas import NewRun
from pipeline.models import (
    CHUNKING_EXPERIMENT,
    EMBEDDINGS_EXPERIMENTS,
    Actor,
    ChunkingExperimentInfo,
    ExperimentState,
    InvalidRequest,
    JsonObject,
    Notifier,
    PipelineRun,
    RunStatus,
)

NEW: JsonObject = {"experiment": {"name": "hybrid · 2024", "chunking": {"chunker": "hybrid", "max_tokens": 126}}}


class Silent(Notifier):
    def notify(self, actor: Actor, payload: JsonObject) -> str | None:
        return None


class Setup:
    def __init__(self) -> None:
        self.fakes, self.store = ExperimentsModules(), MemoryStore()
        self.executor = Executor(self.store, self.fakes.modules, Silent(), ActorRegistry(), lambda r: f"/a/{r.id}")

    def start(self, chunkear: JsonObject, models: list[str], simulate: bool = False) -> NewRun:
        params: dict[str, JsonObject] = {"chunkear": chunkear, "embeber": {"models": [*models]}}
        return NewRun(template="experimentos", files={"sample": 2, "seed": 7}, params=params, simulate=simulate)

    def settle(self, id: str) -> PipelineRun:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            run = self.store.run(id)
            if run is not None and self.executor.status(run) not in (RunStatus.RUNNING, RunStatus.QUEUED):
                return run
            time.sleep(0.01)
        raise AssertionError(f"the run {id} didn't settle")


@pytest.fixture
def setup() -> Setup:
    return Setup()


@pytest.mark.integration
def test_a_new_experiment_embedded_with_two_models(setup: Setup) -> None:
    started = start_run(setup.store, setup.executor, setup.start(NEW, ["minilm", "e5"]), Response())
    assert started.run is not None
    run = setup.settle(started.run.id)
    assert run.status == RunStatus.DONE, run.error
    assert setup.fakes.data.asked[0][:2] == ("parsed", {"sample": 2, "seed": 7})
    assert run.artifacts[CHUNKING_EXPERIMENT] == "c1" and run.artifacts[EMBEDDINGS_EXPERIMENTS] == ["e1", "e2"]
    assert [b["model"] for b in setup.fakes.embeddings.created] == ["minilm", "e5"]


def test_simulate_answers_the_batch_and_what_it_would_do_with_each_model(setup: Setup) -> None:
    setup.fakes.chunking.experiments["c9"] = ChunkingExperimentInfo(
        "c9", "finished", {"tokenizer": "minilm", "max_tokens": 100}
    )
    setup.fakes.data.had["c9"] = {"p0", "p1", "p2"}
    new = setup.start({"extend": "c9"}, ["minilm"], simulate=True)
    started = start_run(setup.store, setup.executor, new, Response())
    assert started.batch == ["p3", "p4"] and setup.store.saved_runs == {}
    assert started.plan == {
        "documents": 2,
        "mode": "extend",
        "experiment": "c9",
        "already": 3,
        "models": [{"model": "minilm", "action": "create"}],
    }


def test_a_model_that_doesnt_fit_the_experiment_to_extend_never_starts(setup: Setup) -> None:
    setup.fakes.chunking.experiments["c9"] = ChunkingExperimentInfo(
        "c9", "finished", {"tokenizer": "minilm", "max_tokens": 100}
    )
    with pytest.raises(InvalidRequest, match="bge doesn't fit"):
        start_run(setup.store, setup.executor, setup.start({"extend": "c9"}, ["bge"]), Response())
    assert setup.store.saved_runs == {}


@pytest.mark.integration
def test_a_failed_chunking_experiment_stops_the_run_and_resume_resumes_it(setup: Setup) -> None:
    setup.fakes.data.states["c1"] = ExperimentState("c1", "failed", "the server stopped")
    started = start_run(setup.store, setup.executor, setup.start(NEW, ["minilm"]), Response())
    assert started.run is not None
    run = setup.settle(started.run.id)
    assert run.status == RunStatus.FAILED and "ended failed" in (run.error or "")
    setup.fakes.chunking.experiments["c1"] = ChunkingExperimentInfo("c1", "failed", {})
    setup.fakes.data.states["c1"] = ExperimentState("c1", "finished")
    setup.executor.resume(run.id)
    run = setup.settle(run.id)
    assert run.status == RunStatus.DONE, run.error
    assert setup.fakes.chunking.resumed == ["c1"] and len(setup.fakes.chunking.started) == 1
