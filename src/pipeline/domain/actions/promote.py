"""The promotions: what a cycle approved, copied to the official graph by chunking."""

from pipeline.models import (
    APPROVED_CHUNKS,
    APPROVED_CONVERSION,
    FILE_BATCH,
    JSON_BATCH,
    OFFICIAL_CHUNKS,
    OFFICIAL_JSON,
    Action,
    ActionContext,
    ActionError,
    ActionOutput,
    JsonValue,
    StageKind,
    json_list,
)


def _promote(context: ActionContext, approved: str, batch: str, gives: str) -> ActionOutput:
    experiment = context.artifacts.get(approved)
    if not isinstance(experiment, str):
        raise ActionError(f"{context.stage.id}: there is no {approved}")
    promotion = context.modules.chunking.promote(experiment)
    failures: list[JsonValue] = [{"sha256": s, "error": e} for s, e in promotion.failed]
    if promotion.count == 0:
        raise ActionError(f"the experiment {experiment} promoted nothing: {failures}")
    if promotion.promoted is not None:
        promoted = list(promotion.promoted)
    else:  # only the number came: the batch without the failures
        source = context.artifacts.get(batch)
        rejected = {s for s, _ in promotion.failed}
        promoted = [str(s) for s in source if str(s) not in rejected] if isinstance(source, list) else []
    return ActionOutput(
        {gives: json_list(promoted)}, {"experiment": experiment, "promoted": promotion.count, "failed": failures}
    )


class PromoteConversion(Action):
    name = "data.promote_conversion"
    kind = StageKind.TASK
    module = "chunking"  # POST /chunking/experiments/{id}/promote: chunking writes the official JSON in data
    needs = (APPROVED_CONVERSION,)
    gives = (OFFICIAL_JSON,)
    description = "copies the approved conversions to official JSON nodes (linked to their PIAA)"

    def run(self, context: ActionContext) -> ActionOutput:
        return _promote(context, APPROVED_CONVERSION, FILE_BATCH, OFFICIAL_JSON)


class PromoteChunks(Action):
    name = "data.promote_chunks"
    kind = StageKind.TASK
    module = "chunking"
    needs = (APPROVED_CHUNKS,)
    gives = (OFFICIAL_CHUNKS,)
    description = "writes the approved chunks as SECCION/FRAGMENTOS under each official JSON"

    def run(self, context: ActionContext) -> ActionOutput:
        return _promote(context, APPROVED_CHUNKS, JSON_BATCH, OFFICIAL_CHUNKS)
