"""The catalog of actions: one kind of stage per class. A new one = its class here, added to CATALOG."""

from pipeline.models import Action, InvalidTemplate, Stage, StageKind

from .chunking import ChunkingApply, ChunkingExperiment, ChunkingPromote
from .embeddings import EmbeddingsApply, EmbeddingsEmbed, EmbeddingsExperiment
from .llm import LlmApply
from .parsing import ParsingParse, ParsingParseAll
from .select import IngestaChunkable, IngestaRun
from .waits import External, ReviewScore

CATALOG: dict[str, Action] = {
    a.name: a
    for a in (
        IngestaChunkable(),
        IngestaRun(),
        ParsingParseAll(),
        ParsingParse(),
        ChunkingExperiment(),
        ChunkingApply(),
        ChunkingPromote(),
        EmbeddingsEmbed(),
        EmbeddingsExperiment(),
        EmbeddingsApply(),
        LlmApply(),
        ReviewScore(),
        External(),
    )
}
REVIEW_SCORE = ReviewScore.name
# A retry that only changes the llm (feature 050) reuses what these gave in the iteration before: they aren't run.
REUSABLE = frozenset({ChunkingExperiment.name, EmbeddingsExperiment.name})
SELECT = IngestaChunkable.name  # the stage whose batch `simulate` shows


def action(stage: Stage) -> Action:
    """The catalog's action of a stage that isn't a cycle; InvalidTemplate if there is none."""
    found = CATALOG.get(stage.action)
    if found is None:
        raise InvalidTemplate(f"stage {stage.id!r}: unknown action {stage.action!r} (known: {sorted(CATALOG)})")
    return found


def kind(stage: Stage) -> StageKind:
    return StageKind.CYCLE if stage.is_cycle else action(stage).kind


__all__ = ["CATALOG", "REUSABLE", "REVIEW_SCORE", "SELECT", "action", "kind"]
