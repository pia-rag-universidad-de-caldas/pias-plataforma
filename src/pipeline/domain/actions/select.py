"""The selections: they freeze a batch of ingesta's files or of official JSON nodes."""

from pipeline.domain.batches import collect, unique
from pipeline.models import (
    FILE_BATCH,
    JSON_BATCH,
    OFFICIAL_JSON,
    Action,
    ActionContext,
    ActionError,
    ActionOutput,
    InvalidRequest,
    Selection,
    StageKind,
    json_list,
    selection_from_json,
)


def _selection(context: ActionContext, default: Selection | None) -> Selection | None:
    """`files` of the stage's configuration, or `default`."""
    raw = context.config.get("files")
    if raw is None:
        return default
    try:
        return selection_from_json(raw, f"{context.stage.id}.files")
    except InvalidRequest as e:
        raise ActionError(str(e)) from e


def _from_run(context: ActionContext, run_id: str, artifact: str) -> list[str]:
    other = context.store.run(run_id)
    if other is None:
        raise ActionError(f"from_run: there is no run {run_id!r}")
    batch = other.artifacts.get(artifact)
    if not isinstance(batch, list) or not batch:
        raise ActionError(f"from_run: the run {run_id!r} has no {artifact}")
    return [str(s) for s in batch]


class IngestaSelect(Action):
    name = "ingesta.select"
    kind = StageKind.TASK
    module = "ingesta"
    gives = (FILE_BATCH,)
    description = "freezes a batch of chunkable files of ingesta (sha256s)"
    parameters = (
        "files: {all | pages+per_page | sha256s | from_run, types, year, month, week, code}; default: the run's"
    )

    def run(self, context: ActionContext) -> ActionOutput:
        selection = _selection(context, context.run.files)
        if selection is None:
            raise ActionError("no files to select: the run has no `files` and the stage no `files` param")
        ingesta = context.modules.ingesta
        if selection.from_run:
            batch = _from_run(context, selection.from_run, FILE_BATCH)
        elif selection.sha256s:
            batch = unique(list(selection.sha256s))
            missing = [s for s in batch if not ingesta.has(s)]
            if missing:
                raise ActionError(f"no chunkable file has these sha256s: {missing}")
        else:

            def fetch(page: int, per_page: int) -> tuple[tuple[str, ...], int, str | None]:
                found = ingesta.page(selection, page, per_page)
                return found.sha256s, found.pages, found.reorganized

            batch = collect(selection, fetch)
        if not batch:
            raise ActionError("the selection has no files")
        return ActionOutput({FILE_BATCH: json_list(batch)}, {"files": len(batch)})


class DataSelectJson(Action):
    name = "data.select_json"
    kind = StageKind.TASK
    module = "data"
    needs = (OFFICIAL_JSON,)
    gives = (JSON_BATCH,)
    description = "freezes a batch of official JSON nodes (by default, the ones this run promoted)"
    parameters = "files: {all | pages+per_page | sha256s | from_run}; default: the json_oficial of the run"

    def run(self, context: ActionContext) -> ActionOutput:
        selection = _selection(context, None)
        if selection is not None and selection.filtered:
            raise ActionError(f"{context.stage.id}.files: the JSON nodes take no filters")
        if selection is None:
            official = context.artifacts.get(OFFICIAL_JSON)
            batch = [str(s) for s in official] if isinstance(official, list) else []
        elif selection.from_run:
            batch = _from_run(context, selection.from_run, JSON_BATCH)
        elif selection.sha256s:
            batch = unique(list(selection.sha256s))
        else:
            data = context.modules.data

            def fetch(page: int, per_page: int) -> tuple[tuple[str, ...], int, str | None]:
                found = data.json_page(page, per_page)
                return found.ids, found.pages, None

            batch = collect(selection, fetch)
        if not batch:
            raise ActionError("the selection has no official JSON")
        return ActionOutput({JSON_BATCH: json_list(batch)}, {"documents": len(batch)})
