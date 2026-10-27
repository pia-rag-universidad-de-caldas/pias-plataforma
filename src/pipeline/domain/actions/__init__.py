"""The catalog of actions: one kind of stage per class. A new one = its class here, added to CATALOG."""

from pipeline.models import Action, InvalidTemplate, Stage, StageKind

from .experiments import ChunkingChunk, ChunkingConvert
from .promote import PromoteChunks, PromoteConversion
from .select import DataSelectJson, IngestaSelect
from .waits import External, ReviewScore

CATALOG: dict[str, Action] = {
    a.name: a
    for a in (
        IngestaSelect(),
        ChunkingConvert(),
        ReviewScore(),
        PromoteConversion(),
        DataSelectJson(),
        ChunkingChunk(),
        PromoteChunks(),
        External(),
    )
}
REVIEW_SCORE = ReviewScore.name


def action(stage: Stage) -> Action:
    """The catalog's action of a stage that isn't a cycle; InvalidTemplate if there is none."""
    found = CATALOG.get(stage.action)
    if found is None:
        raise InvalidTemplate(f"stage {stage.id!r}: unknown action {stage.action!r} (known: {sorted(CATALOG)})")
    return found


def kind(stage: Stage) -> StageKind:
    return StageKind.CYCLE if stage.is_cycle else action(stage).kind


__all__ = ["CATALOG", "REVIEW_SCORE", "action", "kind"]
