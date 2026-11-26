"""Production by batch and by parts (feature 056): the parts block, the 422 of what isn't read, and the engine taking
each part through every stage of the block before the next one."""

from typing import cast

import pytest

from pipeline.domain import LABORATORY, PRODUCTION, Engine
from pipeline.domain.parts import part_block, split
from pipeline.models import (
    CHUNKED,
    EMBEDDED,
    FILE_BATCH,
    PARSED,
    RAW_FILES,
    ActionOutput,
    InvalidRequest,
    JsonObject,
    Modules,
    PartStatus,
    PipelineRun,
    RunRequest,
    RunStatus,
    RunStore,
    Selection,
    Stage,
    StageKind,
    Template,
)

NOW = "2026-11-10T10:00:00-05:00"


def _production(files: Selection | None = None, part_size: int | None = None) -> PipelineRun:
    request = RunRequest(PRODUCTION.id, "test", files, {}, part_size)
    return Engine.start(Engine.new("r1", request, PRODUCTION, NOW), NOW)


def _task(run: PipelineRun, name: str, output: ActionOutput | None = None) -> PipelineRun:
    step = Engine.next(run)
    assert step is not None and step.kind == StageKind.TASK and step.action.name == name
    return Engine.done(run, output or ActionOutput(), NOW)


def _batch(run: PipelineRun) -> list[str]:
    """The batch the stages of the running part see."""
    assert run.part is not None
    return list(run.part.sha256s)


def test_the_parts_block_of_production_is_parse_chunk_embed() -> None:
    assert part_block(PRODUCTION.stages) == (1, 4)
    assert part_block(LABORATORY.stages) is None


def test_split_makes_parts_of_the_size_or_one_part() -> None:
    assert [p.sha256s for p in split(["a", "b", "c"], 2)] == [("a", "b"), ("c",)]
    assert [p.sha256s for p in split(["a", "b", "c"], None)] == [("a", "b", "c")]
    assert split([], 2) == ()


@pytest.mark.parametrize(
    ("template", "files", "part_size", "match"),
    [
        (Template("t", "t", "", (Stage("i", "ingesta.run"),)), Selection(all=True), None, "`files` only goes"),
        (LABORATORY, None, 10, "`part_size` only goes"),
        (PRODUCTION, None, 0, "at least 1"),
    ],
)
def test_files_or_part_size_a_template_doesnt_read_is_refused(
    template: Template, files: Selection | None, part_size: int | None, match: str
) -> None:
    with pytest.raises(InvalidRequest, match=match):
        Engine.new("r1", RunRequest(template.id, "", files, {}, part_size), template, NOW)


def test_scope_all_doesnt_go_with_parts() -> None:
    params: dict[str, JsonObject] = {"chunkear": {"scope": "all"}}
    with pytest.raises(InvalidRequest, match="scope all"):
        Engine.new("r1", RunRequest(PRODUCTION.id, "", None, params, 5), PRODUCTION, NOW)


def test_production_with_files_freezes_the_batch_and_parses_only_it() -> None:
    run = _task(_production(Selection(sha256s=("a", "b"))), "ingesta.run", ActionOutput({RAW_FILES: "i1"}))
    assert Engine.stage_id(run) == "partes"
    run = _task(run, "pipeline.parts", ActionOutput({FILE_BATCH: ["a", "b"]}))
    assert [p.sha256s for p in run.parts] == [("a", "b")]  # without part_size: one part
    assert _batch(run) == ["a", "b"]


@pytest.mark.integration
def test_each_part_goes_through_every_stage_before_the_next() -> None:
    run = _task(_production(part_size=2), "ingesta.run", ActionOutput({RAW_FILES: "i1"}))
    run = _task(run, "pipeline.parts", ActionOutput({FILE_BATCH: ["a", "b", "c"]}))
    order: list[tuple[str, list[str]]] = []
    for part in (["a", "b"], ["c"]):
        assert _batch(run) == part
        for name, artifact in (
            ("parsing.parse_all", PARSED),
            ("chunking.promote", CHUNKED),
            ("embeddings.embed", EMBEDDED),
        ):
            order.append((name, part))
            run = _task(run, name, ActionOutput({artifact: list(part)}))
    assert [n for n, _ in order] == ["parsing.parse_all", "chunking.promote", "embeddings.embed"] * 2
    assert run.status == RunStatus.DONE and [p.status for p in run.parts] == [PartStatus.DONE] * 2
    assert run.artifacts[EMBEDDED] == ["a", "b", "c"]  # what every part gave adds up
    assert [r.part for r in run.records] == [None, None, 1, 1, 1, 2, 2, 2]


def test_a_failure_in_a_part_resumes_that_part_at_its_stage() -> None:
    run = _task(_production(part_size=1), "ingesta.run", ActionOutput({RAW_FILES: "i1"}))
    run = _task(run, "pipeline.parts", ActionOutput({FILE_BATCH: ["a", "b"]}))
    for name, artifact in (
        ("parsing.parse_all", PARSED),
        ("chunking.promote", CHUNKED),
        ("embeddings.embed", EMBEDDED),
    ):
        run = _task(run, name, ActionOutput({artifact: ["a"]}))
    run = _task(run, "parsing.parse_all", ActionOutput({PARSED: ["b"]}))
    run = Engine.fail(run, "chunking down", NOW)
    assert [p.status for p in run.parts] == [PartStatus.DONE, PartStatus.FAILED]
    run = Engine.resume(run, NOW)
    assert run.part is not None and run.part.index == 2 and run.part.status == PartStatus.RUNNING
    run = _task(run, "chunking.promote", ActionOutput({CHUNKED: ["b"]}))  # part 1 isn't repeated
    run = _task(run, "embeddings.embed", ActionOutput({EMBEDDED: ["b"]}))
    assert run.status == RunStatus.DONE and run.artifacts[CHUNKED] == ["a", "b"]


def test_cancel_marks_the_running_part() -> None:
    run = _task(_production(part_size=1), "ingesta.run", ActionOutput({RAW_FILES: "i1"}))
    run = Engine.cancel(_task(run, "pipeline.parts", ActionOutput({FILE_BATCH: ["a", "b"]})), NOW)
    assert [p.status for p in run.parts] == [PartStatus.CANCELLED, PartStatus.PENDING]


def test_an_empty_corpus_without_files_skips_the_block() -> None:
    run = _task(_production(part_size=5), "ingesta.run", ActionOutput({RAW_FILES: "i1"}))
    run = _task(run, "pipeline.parts", ActionOutput({FILE_BATCH: []}))
    assert run.status == RunStatus.DONE and run.parts == ()


def test_production_without_files_nor_parts_has_no_parts() -> None:
    run = _task(_production(), "ingesta.run", ActionOutput({RAW_FILES: "i1"}))
    assert Engine.stage_id(run) == "parsear" and not Engine.batched(run)


def test_a_part_sees_its_own_batch_and_not_what_earlier_parts_gave() -> None:
    run = _task(_production(part_size=1), "ingesta.run", ActionOutput({RAW_FILES: "i1"}))
    run = _task(run, "pipeline.parts", ActionOutput({FILE_BATCH: ["a", "b"]}))
    for name, artifact in (
        ("parsing.parse_all", PARSED),
        ("chunking.promote", CHUNKED),
        ("embeddings.embed", EMBEDDED),
    ):
        run = _task(run, name, ActionOutput({artifact: ["a"]}))
    context = Engine.context(run, cast(Modules, None), cast(RunStore, None))
    assert context.part == 2 and context.artifacts[FILE_BATCH] == ["b"]
    assert PARSED not in context.artifacts and context.artifacts[RAW_FILES] == "i1"
