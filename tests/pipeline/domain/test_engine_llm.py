"""Engine (feature 050): the laboratory's trio chunking + embeddings + llm, without I/O. The iteration keeps its llm,
the inbox shows it, approving leaves it for llm.apply, and a retry that only changes the llm reuses the experiments."""

import pytest

from pipeline.domain import LABORATORY, Engine
from pipeline.models import (
    APPROVED_EMBEDDINGS,
    APPROVED_LLM,
    CHUNKING_EXPERIMENT,
    EMBEDDINGS_EXPERIMENT,
    FILE_BATCH,
    PARSED,
    ActionOutput,
    Decision,
    DecisionKind,
    JsonObject,
    PipelineRun,
    RunRequest,
    RunStatus,
    Selection,
    StageKind,
)

NOW = "2026-11-10T10:00:00-05:00"
LLM: JsonObject = {"model": "qwen", "temperature": 0.2}


def _task(run: PipelineRun, name: str, output: ActionOutput | None = None) -> PipelineRun:
    step = Engine.next(run)
    assert step is not None and step.kind == StageKind.TASK and step.action.name == name
    return Engine.done(run, output or ActionOutput(), NOW)


def _waiting(run: PipelineRun) -> PipelineRun:
    step = Engine.next(run)
    assert step is not None and step.kind == StageKind.WAIT
    return Engine.wait(run, NOW)


def _lab(llm: JsonObject | None = LLM) -> PipelineRun:
    """A laboratory run at its first review, with the trio's llm in the run's params."""
    params: dict[str, JsonObject] = {"laboratorio": {"llm": llm}} if llm else {}
    request = RunRequest(LABORATORY.id, "test", Selection(all=True), params)
    run = Engine.start(Engine.new("r1", request, LABORATORY, NOW), NOW)
    run = _task(run, "ingesta.chunkable", ActionOutput({FILE_BATCH: ["a"]}))
    run = _task(run, "parsing.parse", ActionOutput({PARSED: ["a"]}))
    return _experiments(run, 1)


def _experiments(run: PipelineRun, n: int) -> PipelineRun:
    run = _task(run, "chunking.experiment", ActionOutput({CHUNKING_EXPERIMENT: f"c{n}"}, None, f"c{n}"))
    output = ActionOutput({EMBEDDINGS_EXPERIMENT: f"e{n}"}, None, embeddings_experiment=f"e{n}")
    return _waiting(_task(run, "embeddings.experiment", output))


def _retry(run: PipelineRun, next: JsonObject) -> PipelineRun:
    return Engine.decide(run, Decision(DecisionKind.RETRY, "lab", None, next), "laboratorio", NOW)


def _llm_retry(run: PipelineRun, llm: JsonObject) -> PipelineRun:
    """A retry with only `next.llm`: the next step is already the review, so the run waits for lab again."""
    return _waiting(_retry(run, {"llm": llm}))


def test_the_iteration_keeps_its_llm_and_the_inbox_shows_it() -> None:
    run = _lab()
    assert run.iterations[0].llm == LLM
    item = Engine.inbox_item(run, "/answer")
    assert item is not None and item.llm == LLM and item.embeddings_experiment == "e1"


def test_a_retry_with_only_the_llm_reuses_the_experiments() -> None:
    run = _llm_retry(_lab(), {"temperature": 0.7})
    assert run.status == RunStatus.WAITING and run.waiting is not None and run.waiting.iteration == 2
    second = run.iterations[1]
    assert second.llm == {"model": "qwen", "temperature": 0.7} and second.reused == 1
    assert (second.experiments, second.embedding_experiments) == (("c1",), ("e1",))
    assert second.artifacts == {CHUNKING_EXPERIMENT: "c1", EMBEDDINGS_EXPERIMENT: "e1"}
    reused = [r for r in run.records if r.iteration == 2]
    assert [r.stage for r in reused] == ["chunkear", "embeber"]
    assert all(isinstance(r.result, dict) and r.result["reused_from"] == 1 for r in reused)
    item = Engine.inbox_item(run, "/answer")
    assert item is not None and (item.experiment, item.embeddings_experiment) == ("c1", "e1")


def test_two_llm_retries_in_a_row_reuse_the_first_iterations_experiments() -> None:
    run = _llm_retry(_llm_retry(_lab(), {"temperature": 0.7}), {"temperature": 0.9})
    assert run.iterations[2].reused == 1 and run.iterations[2].experiments == ("c1",)


@pytest.mark.parametrize("next", [{"chunking": {"max_tokens": 64}}, {"llm": {"temperature": 1}, "embeddings": {}}])
def test_a_retry_that_changes_more_than_the_llm_runs_the_experiments_again(next: JsonObject) -> None:
    run = _retry(_lab(), next)
    assert run.status == RunStatus.RUNNING and run.iterations[1].reused is None
    assert run.iterations[1].artifacts == {}
    step = Engine.next(run)
    assert step is not None and step.action.name == "chunking.experiment"


def test_approving_leaves_the_iterations_llm_for_llm_apply() -> None:
    run = _llm_retry(_lab(), {"temperature": 0.7})
    run = Engine.decide(run, Decision(DecisionKind.APPROVE, "lab", 1), "laboratorio", NOW)
    assert run.artifacts[APPROVED_LLM] == LLM and run.artifacts[APPROVED_EMBEDDINGS] == "e1"
    run = _task(run, "chunking.apply")
    run = _task(run, "embeddings.apply")
    step = Engine.next(run)
    assert step is not None and step.action.name == "llm.apply"
