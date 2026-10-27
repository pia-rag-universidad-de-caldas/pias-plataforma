"""Engine (feature 028): the run's state machine through the whole `piaa` template, without I/O."""

import pytest

from pipeline.domain import PIAA, Engine
from pipeline.models import (
    APPROVED_CHUNKS,
    APPROVED_CONVERSION,
    CYCLE,
    EMBEDDINGS,
    FILE_BATCH,
    ActionOutput,
    Completion,
    ConflictError,
    Decision,
    DecisionKind,
    InvalidRequest,
    IterationStatus,
    JsonObject,
    PipelineRun,
    RunRequest,
    RunStatus,
    Selection,
    Stage,
    StageKind,
    Template,
)

NOW = "2026-10-24T10:00:00-05:00"


def _run(template: Template = PIAA, params: dict[str, JsonObject] | None = None) -> PipelineRun:
    request = RunRequest(template.id, "test", Selection(all=True), params or {})
    return Engine.start(Engine.new("r1", request, template, NOW), NOW)


def _task(run: PipelineRun, name: str, output: ActionOutput | None = None) -> PipelineRun:
    step = Engine.next(run)
    assert step is not None and step.kind == StageKind.TASK and step.action.name == name
    return Engine.done(run, output or ActionOutput(), NOW)


def _wait(run: PipelineRun) -> PipelineRun:
    step = Engine.next(run)
    assert step is not None and step.kind == StageKind.WAIT
    return Engine.wait(run, NOW)


def _decide(run: PipelineRun, cycle: str, kind: DecisionKind, **values: object) -> PipelineRun:
    next: JsonObject = {}
    raw = values.get("next")
    if isinstance(raw, dict):
        next = raw
    iteration = values.get("iteration")
    decision = Decision(kind, None, iteration if isinstance(iteration, int) else None, next)
    return Engine.decide(run, decision, cycle, NOW)


def _converted(run: PipelineRun, experiment: str) -> PipelineRun:
    run = _task(run, "chunking.convert", ActionOutput({"conversion": experiment}, None, experiment))
    return _wait(run)


def test_two_retries_then_approve_runs_the_whole_template() -> None:
    run = _run(params={"conversion": {"conversion": {"heading_level": 1, "table_mode": "fast"}}})
    run = _task(run, "ingesta.select", ActionOutput({FILE_BATCH: ["a", "b"]}))
    run = _converted(run, "exp1")
    assert run.status == RunStatus.WAITING and run.waiting is not None
    assert (run.waiting.actor, run.waiting.stage, run.waiting.iteration) == ("lab", "conversion", 1)
    item = Engine.inbox_item(run, "/answer")
    assert item is not None and item.experiment == "exp1" and item.batch == ["a", "b"]

    run = _decide(run, "conversion", DecisionKind.RETRY, next={"conversion": {"heading_level": 2}})
    run = _converted(run, "exp2")
    run = _decide(run, "puntuar_conversion", DecisionKind.RETRY, next={"conversion": {"table_mode": None}})
    iterations = [i for i in run.iterations if i.stage == "conversion"]
    assert [i.status for i in iterations] == [IterationStatus.RETRIED, IterationStatus.RETRIED, IterationStatus.RUNNING]
    assert iterations[2].config == {"conversion": {"heading_level": 2}}  # merged, and null removed table_mode

    run = _converted(run, "exp3")
    run = _decide(run, "conversion", DecisionKind.APPROVE, iteration=2)
    statuses = [i.status for i in run.iterations if i.stage == "conversion"]
    assert statuses == [IterationStatus.RETRIED, IterationStatus.APPROVED, IterationStatus.DISCARDED]
    assert run.artifacts[APPROVED_CONVERSION] == "exp2" and "conversion" not in run.artifacts

    run = _task(run, "data.promote_conversion", ActionOutput({"json_oficial": ["a", "b"]}))
    run = _task(run, "data.select_json", ActionOutput({"lote_json": ["a", "b"]}))
    run = _task(run, "chunking.chunk", ActionOutput({"chunks": "exp4"}, None, "exp4"))
    run = _wait(run)
    assert run.waiting is not None and run.waiting.actor == "lab2"
    run = _decide(run, "chunking", DecisionKind.APPROVE)
    assert run.artifacts[APPROVED_CHUNKS] == "exp4"
    run = _task(run, "data.promote_chunks", ActionOutput({"chunks_oficiales": ["a", "b"]}))

    run = _wait(run)
    assert run.waiting is not None and (run.waiting.actor, run.waiting.step) == ("embeber", "embeber")
    with pytest.raises(ConflictError, match="not for 'lab'"):
        Engine.complete(run, Completion("lab"), "embeber", NOW)
    run = Engine.complete(run, Completion("embeber", {"vectors": 12}), "embeber", NOW)
    assert run.artifacts[EMBEDDINGS] == {"vectors": 12}
    run = _wait(run)
    run = Engine.complete(run, Completion(None, None), "revisar", NOW)
    assert run.status == RunStatus.DONE and run.finished == NOW and Engine.next(run) is None


def _small(max_iterations: int | None) -> Template:
    cycle = Stage(
        "conversion",
        CYCLE,
        actor="lab",
        max_iterations=max_iterations,
        stages=(Stage("convertir", "chunking.convert"), Stage("puntuar", "review.score")),
    )
    return Template("t", "t", "", (Stage("seleccionar", "ingesta.select"), cycle))


def test_max_iterations_leaves_only_approve() -> None:
    run = _task(_run(_small(2)), "ingesta.select", ActionOutput({FILE_BATCH: ["a"]}))
    run = _converted(run, "e1")
    assert run.waiting is not None and not run.waiting.exhausted
    run = _converted(_decide(run, "conversion", DecisionKind.RETRY), "e2")
    assert run.waiting is not None and run.waiting.exhausted
    with pytest.raises(ConflictError, match="max_iterations"):
        _decide(run, "conversion", DecisionKind.RETRY)
    with pytest.raises(InvalidRequest, match="no iteration 7"):
        _decide(run, "conversion", DecisionKind.APPROVE, iteration=7)
    run = _decide(run, "conversion", DecisionKind.APPROVE)
    assert run.status == RunStatus.DONE and run.artifacts[APPROVED_CONVERSION] == "e2"


def test_cancel_discards_the_running_iteration_and_ends() -> None:
    run = _converted(_task(_run(_small(None)), "ingesta.select", ActionOutput({FILE_BATCH: ["a"]})), "e1")
    run = Engine.cancel(run, NOW)
    assert run.status == RunStatus.CANCELLED and run.waiting is None
    assert run.iterations[0].status == IterationStatus.DISCARDED
    with pytest.raises(ConflictError):
        Engine.cancel(run, NOW)
    with pytest.raises(ConflictError):
        Engine.resume(run, NOW)


def test_a_failed_task_resumes_at_the_same_stage() -> None:
    run = _task(_run(_small(None)), "ingesta.select", ActionOutput({FILE_BATCH: ["a"]}))
    run = Engine.fail(run, "the experiment e1 ended failed", NOW)
    assert run.status == RunStatus.FAILED and run.records[-1].status == "failed"
    run = Engine.resume(run, NOW)
    step = Engine.next(run)
    assert run.status == RunStatus.RUNNING and run.error is None
    assert step is not None and step.stage.id == "convertir" and len(run.iterations) == 1


def test_answers_to_a_run_not_waiting_there_are_conflicts() -> None:
    run = _converted(_task(_run(_small(None)), "ingesta.select", ActionOutput({FILE_BATCH: ["a"]})), "e1")
    with pytest.raises(ConflictError, match="not at 'otra'"):
        _decide(run, "otra", DecisionKind.APPROVE)
    with pytest.raises(ConflictError, match="answer it with the route"):
        Engine.complete(run, Completion(), "conversion", NOW)
    with pytest.raises(InvalidRequest, match="only goes with retry"):
        Engine.decide(run, Decision(DecisionKind.APPROVE, next={"x": 1}), "conversion", NOW)


def test_params_for_unknown_stages_are_rejected() -> None:
    with pytest.raises(InvalidRequest, match="nope"):
        Engine.new("r", RunRequest("piaa", "", None, {"nope": {}}), PIAA, NOW)
