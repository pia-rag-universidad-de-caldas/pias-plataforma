"""The stages that run a chunking experiment: conversion only, or chunking of official JSON with a plan."""

from pipeline.models import (
    CHUNKS,
    CONVERSION,
    FILE_BATCH,
    JSON_BATCH,
    Action,
    ActionContext,
    ActionError,
    ActionOutput,
    JsonObject,
    StageKind,
    as_object,
    json_list,
)

FINISHED = "finished"  # chunking's ExperimentStatus of an experiment that ended well
DEFAULT_PLAN: JsonObject = {"rules": [], "default": {"strategy": "hybrid"}}


def _batch(context: ActionContext, artifact: str) -> list[str]:
    batch = context.artifacts.get(artifact)
    if not isinstance(batch, list) or not batch:
        raise ActionError(f"{context.stage.id}: there is no {artifact} to work on")
    return [str(s) for s in batch]


def _name(context: ActionContext) -> str:
    iteration = f" #{context.iteration}" if context.iteration is not None else ""
    return f"{context.run.name} · {context.stage.id}{iteration}"


def _run(context: ActionContext, body: JsonObject, gives: str) -> ActionOutput:
    outcome = context.modules.chunking.run_experiment(body)
    if outcome.status != FINISHED:
        raise ActionError(f"the experiment {outcome.id} ended {outcome.status}: {outcome.error or 'no detail'}")
    return ActionOutput({gives: outcome.id}, {"experiment": outcome.id}, outcome.id)


class ChunkingConvert(Action):
    name = "chunking.convert"
    kind = StageKind.TASK
    module = "chunking"
    needs = (FILE_BATCH,)
    gives = (CONVERSION,)
    description = "converts the batch to JSON with Docling (an experiment without plan), stored in data"
    parameters = "conversion: the `conversion` of POST /chunking/experiments (heading_level, table_mode, include...)"

    def run(self, context: ActionContext) -> ActionOutput:
        body: JsonObject = {
            "name": _name(context),
            "description": f"pipeline {context.run.id}",
            "files": {"sha256s": json_list(_batch(context, FILE_BATCH))},
        }
        conversion = as_object(context.config.get("conversion"), f"{context.stage.id}.conversion")
        if conversion:
            body["conversion"] = conversion
        return _run(context, body, CONVERSION)


class ChunkingChunk(Action):
    name = "chunking.chunk"
    kind = StageKind.TASK
    module = "chunking"
    needs = (JSON_BATCH,)
    gives = (CHUNKS,)
    description = "chunks the official JSON of the batch with a plan by sections, stored in data as an experiment"
    parameters = "plan: the `plan` of POST /chunking/experiments (rules by title or position, default strategy)"

    def run(self, context: ActionContext) -> ActionOutput:
        plan = as_object(context.config.get("plan"), f"{context.stage.id}.plan") or DEFAULT_PLAN
        body: JsonObject = {
            "name": _name(context),
            "description": f"pipeline {context.run.id}",
            "files": {"from_json": {"sha256s": json_list(_batch(context, JSON_BATCH))}},
            "plan": plan,
        }
        return _run(context, body, CHUNKS)
