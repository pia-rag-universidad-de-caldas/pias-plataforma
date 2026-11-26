"""Engine (features 028 and 044): the run's state machine through `produccion` and `laboratorio`, without I/O."""

import pytest

from pipeline.domain import LABORATORY, PRODUCTION, Engine
from pipeline.models import (
    APPROVED_CHUNKING,
    APPROVED_EMBEDDINGS,
    APPROVED_LLM,
    CHUNKED,
    CHUNKING_EXPERIMENT,
    CYCLE,
    EMBEDDED,
    EMBEDDINGS_EXPERIMENT,
    FILE_BATCH,
    PARSED,
    RAW_FILES,
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


def _run(template: Template = LABORATORY, params: dict[str, JsonObject] | None = None) -> PipelineRun:
    files = None if template is PRODUCTION else Selection(all=True)  # production without files: everything missing
    request = RunRequest(template.id, "test", files, params or {})
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
    score = values.get("score")
    decision = Decision(
        kind, None, iteration if isinstance(iteration, int) else None, next, score if isinstance(score, dict) else None
    )
    return Engine.decide(run, decision, cycle, NOW)


def _parsed_batch(run: PipelineRun) -> PipelineRun:
    run = _task(run, "ingesta.chunkable", ActionOutput({FILE_BATCH: ["a", "b"]}))
    return _task(run, "parsing.parse", ActionOutput({PARSED: ["a", "b"]}))


def _iteration(run: PipelineRun, n: int) -> PipelineRun:
    """One laboratory iteration: a chunking experiment, its embeddings experiment, then the wait for lab."""
    run = _task(run, "chunking.experiment", ActionOutput({CHUNKING_EXPERIMENT: f"c{n}"}, None, f"c{n}"))
    run = _task(
        run,
        "embeddings.experiment",
        ActionOutput({EMBEDDINGS_EXPERIMENT: f"e{n}"}, None, embeddings_experiment=f"e{n}"),
    )
    return _wait(run)


@pytest.mark.integration
def test_the_laboratory_retries_then_approves_a_pair_and_applies_both() -> None:
    run = _parsed_batch(_run(params={"laboratorio": {"chunking": {"max_tokens": 100}}}))
    run = _iteration(run, 1)
    assert run.status == RunStatus.WAITING and run.waiting is not None
    assert (run.waiting.actor, run.waiting.stage, run.waiting.iteration) == ("lab", "laboratorio", 1)
    item = Engine.inbox_item(run, "/answer")
    assert item is not None and (item.experiment, item.embeddings_experiment) == ("c1", "e1")
    assert item.batch == ["a", "b"]

    score: JsonObject = {"score": 3, "criteria": {"coherencia": 3}, "author": "lab"}
    run = _decide(run, "laboratorio", DecisionKind.RETRY, next={"chunking": {"max_tokens": 64}}, score=score)
    run = _iteration(run, 2)
    run = _decide(run, "puntuar", DecisionKind.APPROVE)
    iterations = [i for i in run.iterations if i.stage == "laboratorio"]
    assert [i.status for i in iterations] == [IterationStatus.RETRIED, IterationStatus.APPROVED]
    assert iterations[0].score == score and iterations[1].config["chunking"] == {"chunker": "hybrid", "max_tokens": 64}
    assert (iterations[1].experiments, iterations[1].embedding_experiments) == (("c2",), ("e2",))
    assert (run.artifacts[APPROVED_CHUNKING], run.artifacts[APPROVED_EMBEDDINGS]) == ("c2", "e2")

    run = _task(run, "chunking.apply")
    run = _task(run, "embeddings.apply")
    assert APPROVED_LLM not in run.artifacts and item.llm is None  # a cycle without llm: llm.apply has nothing
    run = _task(run, "llm.apply")
    assert run.status == RunStatus.DONE and Engine.next(run) is None


@pytest.mark.integration
def test_production_passes_ids_from_module_to_module_and_ends() -> None:
    run = _run(PRODUCTION)
    run = _task(run, "ingesta.run", ActionOutput({RAW_FILES: "i1"}))
    run = _task(run, "parsing.parse_all", ActionOutput({PARSED: ["a"]}))
    run = _task(run, "chunking.promote", ActionOutput({CHUNKED: ["a"]}))
    run = _task(run, "embeddings.embed", ActionOutput({EMBEDDED: ["a"]}))
    assert run.status == RunStatus.DONE and run.artifacts[EMBEDDED] == ["a"]
    assert [r.stage for r in run.records] == ["ingestar", "parsear", "chunkear", "embeber"]


def _small(max_iterations: int | None) -> Template:
    cycle = Stage(
        "laboratorio",
        CYCLE,
        actor="lab",
        max_iterations=max_iterations,
        stages=(
            Stage("chunkear", "chunking.experiment"),
            Stage("embeber", "embeddings.experiment"),
            Stage("puntuar", "review.score"),
        ),
    )
    stages = (Stage("seleccionar", "ingesta.chunkable"), Stage("p", "parsing.parse"))
    return Template("t", "t", "", (*stages, cycle))


def test_max_iterations_leaves_only_approve() -> None:
    run = _iteration(_parsed_batch(_run(_small(2))), 1)
    assert run.waiting is not None and not run.waiting.exhausted
    run = _iteration(_decide(run, "laboratorio", DecisionKind.RETRY), 2)
    assert run.waiting is not None and run.waiting.exhausted
    with pytest.raises(ConflictError, match="max_iterations"):
        _decide(run, "laboratorio", DecisionKind.RETRY)
    with pytest.raises(InvalidRequest, match="no iteration 7"):
        _decide(run, "laboratorio", DecisionKind.APPROVE, iteration=7)
    run = _decide(run, "laboratorio", DecisionKind.APPROVE)
    assert run.status == RunStatus.DONE and run.artifacts[APPROVED_CHUNKING] == "c2"


def test_cancel_discards_the_running_iteration_and_ends() -> None:
    run = _iteration(_parsed_batch(_run(_small(None))), 1)
    run = Engine.cancel(run, NOW)
    assert run.status == RunStatus.CANCELLED and run.waiting is None
    assert run.iterations[0].status == IterationStatus.DISCARDED
    with pytest.raises(ConflictError):
        Engine.cancel(run, NOW)
    with pytest.raises(ConflictError):
        Engine.resume(run, NOW)


def test_a_failed_task_resumes_at_the_same_stage() -> None:
    run = _parsed_batch(_run(_small(None)))
    run = Engine.fail(run, "the chunking experiment c1 ended failed", NOW)
    assert run.status == RunStatus.FAILED and run.records[-1].status == "failed"
    run = Engine.resume(run, NOW)
    step = Engine.next(run)
    assert run.status == RunStatus.RUNNING and run.error is None
    assert step is not None and step.stage.id == "chunkear" and len(run.iterations) == 1


def test_answers_to_a_run_not_waiting_there_are_conflicts() -> None:
    run = _iteration(_parsed_batch(_run(_small(None))), 1)
    with pytest.raises(ConflictError, match="not at 'otra'"):
        _decide(run, "otra", DecisionKind.APPROVE)
    with pytest.raises(ConflictError, match="answer it with the route"):
        Engine.complete(run, Completion(), "laboratorio", NOW)
    with pytest.raises(InvalidRequest, match="only goes with retry"):
        Engine.decide(run, Decision(DecisionKind.APPROVE, next={"x": 1}), "laboratorio", NOW)


def test_params_for_unknown_stages_are_rejected() -> None:
    with pytest.raises(InvalidRequest, match="nope"):
        Engine.new("r", RunRequest("produccion", "", None, {"nope": {}}), PRODUCTION, NOW)
