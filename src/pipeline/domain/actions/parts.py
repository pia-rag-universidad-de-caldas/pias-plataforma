"""The internal task of a run by batch (feature 056): freezing its batch when it reaches the parts block. It isn't in
the catalog: no template can have it, the engine asks for it."""

from pipeline.domain.parts import PARTS_ACTION, split
from pipeline.models import (
    FILE_BATCH,
    Action,
    ActionContext,
    ActionError,
    ActionOutput,
    Selection,
    StageKind,
    json_list,
)

from .select import selected


class PartsFreeze(Action):
    name = PARTS_ACTION
    kind = StageKind.TASK
    module = "ingesta"
    gives = (FILE_BATCH,)
    description = (
        "freezes the batch of a production run by parts: the run's `files`, or every chunkable file of ingesta (the"
        " current RAW: what is already done is skipped by each module)"
    )

    def run(self, context: ActionContext) -> ActionOutput:
        files = context.run.files
        batch = selected(context, files or Selection(all=True))
        if not batch and files is not None:
            raise ActionError("the selection has no files")
        parts = len(split(batch, context.run.part_size))
        return ActionOutput({FILE_BATCH: json_list(batch)}, {"files": len(batch), "parts": parts})


FREEZE = PartsFreeze()
