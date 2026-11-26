"""Engine.resume of an experiments run (feature 062): resumed at the wait for a chunking experiment, the run goes back
to the stage that started it (which resumes it); at any other stage it repeats that stage."""

from dataclasses import replace

import pytest

from pipeline.domain import EXPERIMENTS, Engine
from pipeline.models import (
    CHUNKING_EXPERIMENT,
    FILE_BATCH,
    ActionOutput,
    Cursor,
    JsonObject,
    PipelineRun,
    RunRequest,
    RunStatus,
)

CHUNKEAR, ESPERAR, EMBEBER = 1, 2, 3


def at(stage: int, status: RunStatus = RunStatus.FAILED) -> PipelineRun:
    request = RunRequest("experimentos", "prueba", None, {"chunkear": {"official": True}})
    run = Engine.start(Engine.new("r1", request, EXPERIMENTS, "t0"), "t0")
    artifacts: JsonObject = {FILE_BATCH: ["p0"], CHUNKING_EXPERIMENT: "c1"}
    return replace(run, status=status, cursor=Cursor(stage), artifacts=artifacts)


@pytest.mark.parametrize("status", [RunStatus.FAILED, RunStatus.INTERRUPTED, RunStatus.RUNNING])
def test_resumed_at_the_wait_it_goes_back_to_the_chunking_stage(status: RunStatus) -> None:
    resumed = Engine.resume(at(ESPERAR, status), "t1")
    assert resumed.cursor == Cursor(CHUNKEAR) and resumed.status == RunStatus.RUNNING
    assert resumed.artifacts[CHUNKING_EXPERIMENT] == "c1"


def test_resumed_at_the_embedding_it_repeats_the_embedding() -> None:
    assert Engine.resume(at(EMBEBER), "t1").cursor == Cursor(EMBEBER)


def test_the_chunking_stage_done_goes_on_to_the_wait() -> None:
    run = replace(at(CHUNKEAR), status=RunStatus.RUNNING)
    assert Engine.done(run, ActionOutput({CHUNKING_EXPERIMENT: "c1"}), "t1").cursor == Cursor(ESPERAR)
