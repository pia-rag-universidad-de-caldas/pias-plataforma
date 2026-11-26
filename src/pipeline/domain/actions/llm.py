"""llm's stage (feature 050): the llm configuration of the approved laboratory iteration becomes llm's active one."""

from pipeline.models import (
    APPROVED_EMBEDDINGS,
    APPROVED_LLM,
    LLM_APPLIED,
    Action,
    ActionContext,
    ActionError,
    ActionOutput,
    StageKind,
)


class LlmApply(Action):
    name = "llm.apply"
    kind = StageKind.TASK
    module = "llm"
    needs = (APPROVED_EMBEDDINGS,)  # the llm was tried over the approved embeddings experiment
    gives = (LLM_APPLIED,)
    description = (
        "the llm configuration of the approved iteration becomes llm's active one (PUT /llm/config); skipped if the"
        " cycle had no llm"
    )
    parameters = "none (it reads the approved iteration's llm: {model, temperature, num_ctx, max_tokens, system})"

    def run(self, context: ActionContext) -> ActionOutput:
        llm = context.artifacts.get(APPROVED_LLM)
        if llm is None:
            return ActionOutput({LLM_APPLIED: None}, {"applied": None, "skipped": "the approved iteration had no llm"})
        if not isinstance(llm, dict):
            raise ActionError(f"{context.stage.id}: {APPROVED_LLM} isn't an object: {llm!r}")
        context.modules.llm.apply(llm)
        return ActionOutput({LLM_APPLIED: llm}, {"applied": llm})


__all__ = ["LlmApply"]
