"""Embeddings' stages (the contract of feature 044): embedding the official chunks with the active configuration
(production), an experiment over a chunking experiment (laboratory) and its configuration made the active one."""

from pipeline.domain.pairing import pair
from pipeline.models import (
    APPROVED_EMBEDDINGS,
    CHUNKED,
    CHUNKING_EXPERIMENT,
    EMBEDDED,
    EMBEDDINGS_APPLIED,
    EMBEDDINGS_EXPERIMENT,
    Action,
    ActionContext,
    ActionError,
    ActionOutput,
    InvalidRequest,
    JsonObject,
    StageKind,
    json_list,
)

from .common import ended_well, ids, run_name


class EmbeddingsEmbed(Action):
    name = "embeddings.embed"
    kind = StageKind.TASK
    module = "embeddings"
    needs = (CHUNKED,)
    gives = (EMBEDDED,)
    description = "embeds the official chunks of the chunked documents with the active configuration, and waits"

    def run(self, context: ActionContext) -> ActionOutput:
        batch = ids(context, CHUNKED)
        if not batch:
            return ActionOutput({EMBEDDED: []}, {"embedded": 0})
        outcome = ended_well("the embeddings run", context.modules.embeddings.embed(batch))
        embedded = list(outcome.sha256s) if outcome.sha256s else batch
        return ActionOutput({EMBEDDED: json_list(embedded)}, {"run": outcome.id, "embedded": len(embedded)})


class EmbeddingsExperiment(Action):
    name = "embeddings.experiment"
    kind = StageKind.TASK
    module = "embeddings"
    needs = (CHUNKING_EXPERIMENT,)
    gives = (EMBEDDINGS_EXPERIMENT,)
    description = (
        "embeds the chunks of the iteration's chunking experiment with its model, apart from the official;"
        " max_tokens = chunking's + the model's special tokens"
    )
    parameters = "embeddings: {model} (the pair of the iteration)"

    def run(self, context: ActionContext) -> ActionOutput:
        experiment = context.artifacts.get(CHUNKING_EXPERIMENT)
        if not isinstance(experiment, str):
            raise ActionError(f"{context.stage.id}: there is no {CHUNKING_EXPERIMENT}")
        try:
            fitted = pair(context.config, context.modules.embeddings.models())
        except InvalidRequest as e:
            raise ActionError(str(e)) from e
        body: JsonObject = {
            "name": run_name(context),
            "description": f"pipeline {context.run.id}",
            "chunking_experiment": experiment,
            **fitted.embeddings,
        }
        outcome = ended_well("the embeddings experiment", context.modules.embeddings.experiment(body))
        result: JsonObject = {
            "experiment": outcome.id,
            "chunking_experiment": experiment,
            "embeddings": fitted.embeddings,
        }
        return ActionOutput({EMBEDDINGS_EXPERIMENT: outcome.id}, result, embeddings_experiment=outcome.id)


class EmbeddingsApply(Action):
    name = "embeddings.apply"
    kind = StageKind.TASK
    module = "embeddings"
    needs = (APPROVED_EMBEDDINGS,)
    gives = (EMBEDDINGS_APPLIED,)
    description = "the approved embeddings experiment's configuration becomes the active one"

    def run(self, context: ActionContext) -> ActionOutput:
        experiment = context.artifacts.get(APPROVED_EMBEDDINGS)
        if not isinstance(experiment, str):
            raise ActionError(f"{context.stage.id}: there is no {APPROVED_EMBEDDINGS}")
        context.modules.embeddings.apply(experiment)
        return ActionOutput({EMBEDDINGS_APPLIED: experiment}, {"applied": experiment})


__all__ = ["EmbeddingsApply", "EmbeddingsEmbed", "EmbeddingsExperiment"]
