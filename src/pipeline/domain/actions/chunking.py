"""Chunking's stages (feature 043): an experiment over the parsed batch (laboratory), its configuration made the active
one, and chunking with the active configuration into the official graph (production)."""

from pipeline.config import SCOPES
from pipeline.domain.batches import collect
from pipeline.domain.pairing import pair
from pipeline.models import (
    APPROVED_CHUNKING,
    CHUNKED,
    CHUNKING_APPLIED,
    CHUNKING_EXPERIMENT,
    PARSED,
    Action,
    ActionContext,
    ActionError,
    ActionOutput,
    InvalidRequest,
    JsonObject,
    Selection,
    StageKind,
    json_list,
)

from .common import ended_well, ids, run_name

NEW, ALL = SCOPES


def _all_parsed(context: ActionContext) -> list[str]:
    """Every JSON node in data (scope all): chunking says `sin_parseo` of the ones without a DoclingDocument."""
    data = context.modules.data

    def fetch(page: int, per_page: int) -> tuple[tuple[str, ...], int, str | None]:
        found = data.json_page(page, per_page)
        return found.ids, found.pages, None

    return collect(Selection(all=True), fetch)


class ChunkingExperiment(Action):
    name = "chunking.experiment"
    kind = StageKind.TASK
    module = "chunking"
    needs = (PARSED,)
    gives = (CHUNKING_EXPERIMENT,)
    description = (
        "chunks the parsed batch with the iteration's configuration, apart from the official (POST"
        " /chunking/experiments); its tokenizer is the embeddings model and its max_tokens fits the model"
    )
    parameters = "chunking: {chunker, max_tokens, merge_peers}; embeddings: {model} (the pair of the iteration)"

    def run(self, context: ActionContext) -> ActionOutput:
        batch = ids(context, PARSED)
        if not batch:
            raise ActionError(f"{context.stage.id}: none of the batch is parsed")
        try:
            fitted = pair(context.config, context.modules.embeddings.models())
        except InvalidRequest as e:
            raise ActionError(str(e)) from e
        body: JsonObject = {
            "name": run_name(context),
            "description": f"pipeline {context.run.id}",
            "sha256s": json_list(batch),
            "chunking": fitted.chunking,
        }
        outcome = ended_well("the chunking experiment", context.modules.chunking.experiment(body))
        result: JsonObject = {"experiment": outcome.id, "chunking": fitted.chunking, "chunked": len(outcome.sha256s)}
        return ActionOutput({CHUNKING_EXPERIMENT: outcome.id}, result, outcome.id)


class ChunkingApply(Action):
    name = "chunking.apply"
    kind = StageKind.TASK
    module = "chunking"
    needs = (APPROVED_CHUNKING,)
    gives = (CHUNKING_APPLIED,)
    description = "the approved chunking experiment's configuration becomes the active one (POST .../apply)"

    def run(self, context: ActionContext) -> ActionOutput:
        experiment = context.artifacts.get(APPROVED_CHUNKING)
        if not isinstance(experiment, str):
            raise ActionError(f"{context.stage.id}: there is no {APPROVED_CHUNKING}")
        context.modules.chunking.apply(experiment)
        return ActionOutput({CHUNKING_APPLIED: experiment}, {"applied": experiment})


class ChunkingPromote(Action):
    name = "chunking.promote"
    kind = StageKind.TASK
    module = "chunking"
    needs = (PARSED,)
    gives = (CHUNKED,)
    description = (
        "chunks with the active configuration into the official graph (POST /chunking/runs) and waits:"
        " the just parsed (scope new) or every parsed document (scope all)"
    )
    parameters = "scope: new (default) | all"

    def run(self, context: ActionContext) -> ActionOutput:
        scope = context.config.get("scope") or NEW
        if scope not in SCOPES:
            raise ActionError(f"{context.stage.id}.scope must be one of {list(SCOPES)}, not {scope!r}")
        batch = _all_parsed(context) if scope == ALL else ids(context, PARSED)
        if not batch:
            return ActionOutput({CHUNKED: []}, {"scope": scope, "chunked": 0})
        outcome = ended_well("the chunking run", context.modules.chunking.promote(batch))
        chunked = list(outcome.sha256s)
        result: JsonObject = {"run": outcome.id, "scope": scope, "chunked": len(chunked), "asked": len(batch)}
        return ActionOutput({CHUNKED: json_list(chunked)}, result)
