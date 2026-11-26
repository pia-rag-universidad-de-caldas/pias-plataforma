"""Ingesta's stages: freezing a batch of its chunkable files, and running an ingestion (which puts the current files
in data as RAW nodes, feature 042)."""

from pipeline.domain.batches import collect, sampled, unique
from pipeline.domain.codec import selection_from_json
from pipeline.models import (
    FILE_BATCH,
    RAW_FILES,
    Action,
    ActionContext,
    ActionError,
    ActionOutput,
    InvalidRequest,
    Selection,
    StageKind,
    json_list,
)

from .common import ended_well


def _selection(context: ActionContext) -> Selection | None:
    """`files` of the stage's configuration, or the run's."""
    raw = context.config.get("files")
    if raw is None:
        return context.run.files
    try:
        return selection_from_json(raw, f"{context.stage.id}.files")
    except InvalidRequest as e:
        raise ActionError(str(e)) from e


def _from_run(context: ActionContext, run_id: str) -> list[str]:
    other = context.store.run(run_id)
    if other is None:
        raise ActionError(f"from_run: there is no run {run_id!r}")
    batch = other.artifacts.get(FILE_BATCH)
    if not isinstance(batch, list) or not batch:
        raise ActionError(f"from_run: the run {run_id!r} has no {FILE_BATCH}")
    return [str(s) for s in batch]


def selected(context: ActionContext, selection: Selection) -> list[str]:
    """The sha256s of ingesta's chunkable files `selection` takes, frozen now (possibly none)."""
    ingesta = context.modules.ingesta
    if selection.from_run:
        return _from_run(context, selection.from_run)
    if selection.sha256s:
        batch = unique(list(selection.sha256s))
        missing = [s for s in batch if not ingesta.has(s)]
        if missing:
            raise ActionError(f"no chunkable file has these sha256s: {missing}")
        return batch

    def fetch(page: int, per_page: int) -> tuple[tuple[str, ...], int, str | None]:
        found = ingesta.page(selection, page, per_page)
        return found.sha256s, found.pages, found.reorganized

    if selection.sample is not None:  # after the filters, over every page (feature 062)
        return sampled(collect(selection, fetch), selection.sample, selection.seed)
    return collect(selection, fetch)


class IngestaChunkable(Action):
    name = "ingesta.chunkable"
    kind = StageKind.TASK
    module = "ingesta"
    gives = (FILE_BATCH,)
    description = "freezes a batch of chunkable files of ingesta (sha256s): every iteration works on the same"
    parameters = "files: {all | pages+per_page | sha256s | from_run, types, year, month, week}; default: the run's"

    def run(self, context: ActionContext) -> ActionOutput:
        selection = _selection(context)
        if selection is None:
            raise ActionError("no files to select: the run has no `files` and the stage no `files` param")
        batch = selected(context, selection)
        if not batch:
            raise ActionError("the selection has no files")
        return ActionOutput({FILE_BATCH: json_list(batch)}, {"files": len(batch)})


class IngestaRun(Action):
    name = "ingesta.run"
    kind = StageKind.TASK
    module = "ingesta"
    gives = (RAW_FILES,)
    description = (
        "runs an ingestion (POST /ingesta/runs): organizes what is new and puts every current file in data as RAW;"
        " waits for another one that is running"
    )

    def run(self, context: ActionContext) -> ActionOutput:
        outcome = ended_well("the ingestion", context.modules.ingesta.ingest(context.watch))
        return ActionOutput({RAW_FILES: outcome.id}, {"ingestion": outcome.id})
