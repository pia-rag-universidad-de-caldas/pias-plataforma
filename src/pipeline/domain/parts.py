"""A production run by parts (feature 056), without I/O.

The parts block of a template is the longest run of top-level stages that can go a part at a time (parse, official
chunking, embedding) around its `chunking.promote`: in `produccion`, parsear → chunkear → embeber. A run goes by batch
when it has `part_size`, or `files` and no stage that selects them (ingesta.chunkable): its batch is frozen when it
reaches the block (or taken from the stage that selected it) and split into parts, and each part goes through every
stage of the block before the next one starts.
"""

from collections.abc import Sequence

from pipeline.models import CHUNKED, EMBEDDED, FILE_BATCH, PARSED, InvalidRequest, JsonObject, Part, RunRequest, Stage

from .merge import deep_merge

PART_ACTIONS = frozenset({"parsing.parse_all", "parsing.parse", "chunking.promote", "embeddings.embed"})
ANCHOR = "chunking.promote"  # a block is built around the official chunking
PART_GIVES = frozenset({PARSED, CHUNKED, EMBEDDED})  # what the block's stages give for each part (added up in the run)
SELECT_ACTIONS = frozenset({"ingesta.chunkable", "data.parsed"})  # the stages that read `files` themselves
PARTS_ACTION = "pipeline.parts"  # the internal task that freezes the batch (it isn't in the catalog)
PARTS_STAGE = Stage("partes", PARTS_ACTION)  # how that task shows in the records


def part_block(stages: Sequence[Stage]) -> tuple[int, int] | None:
    """(first, past the last) index of the parts block among the top-level stages; None if there is none."""
    anchor = next((i for i, s in enumerate(stages) if s.action == ANCHOR), None)
    if anchor is None:
        return None
    start, end = anchor, anchor + 1
    while start > 0 and stages[start - 1].action in PART_ACTIONS:
        start -= 1
    while end < len(stages) and stages[end].action in PART_ACTIONS:
        end += 1
    return start, end


def selects(stages: Sequence[Stage]) -> bool:
    return any(s.action in SELECT_ACTIONS for s in stages)


def batched(stages: Sequence[Stage], has_files: bool, part_size: int | None) -> bool:
    """Whether a run goes by batch through the parts block (and so has parts)."""
    if part_block(stages) is None:
        return False
    return part_size is not None or (has_files and not selects(stages))


def check_parts(stages: Sequence[Stage], request: RunRequest) -> None:
    """InvalidRequest (422) for `files` or `part_size` the template doesn't read, and for scope all by batch."""
    block = part_block(stages)
    if request.files is not None and block is None and not selects(stages):
        raise InvalidRequest(
            "`files` only goes with a template that selects files (ingesta.chunkable, data.parsed) or chunks into"
            " the official graph (produccion)"
        )
    if request.part_size is not None:
        if request.part_size < 1:
            raise InvalidRequest("part_size must be at least 1")
        if block is None:
            raise InvalidRequest(
                "`part_size` only goes with a template that chunks into the official graph (produccion)"
            )
    if block is None or not batched(stages, request.files is not None, request.part_size):
        return
    for stage in stages[block[0] : block[1]]:
        config: JsonObject = deep_merge(stage.params, request.params.get(stage.id, {}))
        if stage.action == ANCHOR and config.get("scope") == "all":
            raise InvalidRequest(
                "scope all goes over every parsed document: it doesn't go with `files` nor `part_size`"
            )


def split(batch: Sequence[str], size: int | None) -> tuple[Part, ...]:
    """The batch in parts of `size` (one part without it); none for an empty batch."""
    if not batch:
        return ()
    step = size or len(batch)
    return tuple(Part(n + 1, tuple(batch[i : i + step])) for n, i in enumerate(range(0, len(batch), step)))


def merged(run_artifacts: JsonObject, part_artifacts: JsonObject) -> JsonObject:
    """The run's artifacts plus what a finished part gave: lists of sha256s add up, the rest is replaced."""
    merged_: JsonObject = dict(run_artifacts)
    for key, value in part_artifacts.items():
        if key == FILE_BATCH:
            continue
        before = merged_.get(key)
        if isinstance(value, list) and isinstance(before, list):
            merged_[key] = [*before, *(v for v in value if v not in before)]
        else:
            merged_[key] = value
    return merged_
