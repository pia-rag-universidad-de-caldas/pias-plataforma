"""The stages of the experiments pipeline (feature 062): choosing parsed documents with data, putting them in a chunking
experiment (new, or one that exists), waiting until data says it ended, and embedding its chunks with one or more
models (or the official chunks, next to the active model). Each module gets explicit lists; the pipeline chooses."""

import secrets
from collections.abc import Callable

from pipeline.config import CHUNKING_GOES_ON, CHUNKING_RESUMABLE, MAX_SELECT_PER_PAGE, PARSED_UNIVERSE, SEED_LIMIT
from pipeline.domain.batches import unique
from pipeline.domain.codec import selection_from_json, selection_to_json
from pipeline.domain.experiments import ALIVE, EXCLUDE, EXPERIMENT, MODELS, OFFICIAL, UNIVERSE, mode, models
from pipeline.domain.pairing import HYBRID, chosen_models, chunk_fit, embeddings_limit
from pipeline.models import (
    CHUNKING_EXPERIMENT,
    EMBEDDED,
    EMBEDDINGS_EXPERIMENTS,
    FILE_BATCH,
    Action,
    ActionContext,
    ActionError,
    ActionOutput,
    EmbeddingModel,
    InvalidRequest,
    JobOutcome,
    JsonObject,
    JsonValue,
    PipelineError,
    Selection,
    StageKind,
    as_object,
    json_list,
)

from .common import ids, run_name


def _selection(context: ActionContext) -> Selection:
    """`files` of the stage, or the run's, or every document; a `from_run` becomes that run's batch."""
    raw = context.config.get("files")
    try:
        selection = context.run.files if raw is None else selection_from_json(raw, f"{context.stage.id}.files")
    except InvalidRequest as e:
        raise ActionError(str(e)) from e
    if selection is None:
        return Selection(all=True)
    if selection.from_run is None:
        return selection
    other = context.store.run(selection.from_run)
    batch = None if other is None else other.artifacts.get(FILE_BATCH)
    if not isinstance(batch, list) or not batch:
        raise ActionError(f"from_run: the run {selection.from_run!r} has no {FILE_BATCH}")
    return Selection(sha256s=tuple(str(s) for s in batch))


def seeded(files: JsonObject, draw: Callable[[], int] = lambda: secrets.randbelow(SEED_LIMIT)) -> JsonObject:
    """A sample without a seed gets one, drawn once: data draws such a sample again on every page, so reading it page by
    page would repeat and miss documents. The seed stays in the selection, so a resume takes the same sample."""
    if files.get("sample") is None or files.get("seed") is not None:
        return files
    return {**files, "seed": draw()}


def selected(context: ActionContext) -> tuple[list[str], JsonObject]:
    """The sha256s data gives for the stage's selection, every page of them, and the selection as it was asked (with
    the seed it was drawn with, if it is a sample)."""
    files = seeded(selection_to_json(_selection(context)))
    universe = str(context.config.get(UNIVERSE) or PARSED_UNIVERSE)
    exclude = context.config.get(EXCLUDE)
    excluded = exclude if isinstance(exclude, str) else None
    found: list[str] = []
    page = 1
    while True:
        answer = context.modules.data.select(universe, files, excluded, page, MAX_SELECT_PER_PAGE)
        found += answer.sha256s
        if page >= answer.pages:
            break
        page += 1
    return unique(found), files


def _mode(context: ActionContext) -> tuple[str, JsonValue]:
    try:
        return mode(context.config, context.stage.id)
    except InvalidRequest as e:
        raise ActionError(str(e)) from e


def _models(context: ActionContext) -> list[EmbeddingModel]:
    try:
        names = models(context.config, context.stage.id)
        return chosen_models(names, context.modules.embeddings.models()) if names else []
    except InvalidRequest as e:
        raise ActionError(str(e)) from e


class DataParsed(Action):
    name = "data.parsed"
    kind = StageKind.TASK
    module = "data"
    gives = (FILE_BATCH,)
    description = (
        "freezes the batch: the parsed documents the selection takes, as data answers them (POST"
        " /data/documents/select, every page); official: the officially chunked; extend: without those the"
        " experiment already has"
    )
    parameters = (
        "files: {all | pages+per_page | sha256s | sample (+seed) | from_run, types, year, month, week}; default:"
        " the run's, or all. universe and exclude_experiment come from the chunking stage"
    )

    def run(self, context: ActionContext) -> ActionOutput:
        batch, files = selected(context)
        excluded = context.config.get(EXCLUDE)
        if not batch and excluded is None:
            raise ActionError("the selection has no documents in data")
        result: JsonObject = {"files": len(batch), "universe": context.config.get(UNIVERSE) or PARSED_UNIVERSE}
        if excluded is not None:
            result["excluded"] = excluded
        result["selection"] = files
        return ActionOutput({FILE_BATCH: json_list(batch)}, result)


class ChunkingExtend(Action):
    name = "chunking.extend"
    kind = StageKind.TASK
    module = "chunking"
    needs = (FILE_BATCH,)
    gives = (CHUNKING_EXPERIMENT,)
    description = (
        "puts the batch in a chunking experiment and doesn't wait (data says when it ended): a new one (POST"
        " /chunking/experiments, counting the chunks with every model's tokenizer: fit), or one that exists (POST"
        " /chunking/experiments/{id}/documents: only what it didn't have; nothing new, nothing is chunked); official:"
        " nothing. Resumed, it resumes the experiment (POST .../resume) if it stopped half-way"
    )
    parameters = (
        "exactly one of experiment: {name?, description?, chunking: {chunker, max_tokens?, merge_peers?}} | extend:"
        " <id> | official: true; models: those of the embeddings stage"
    )

    def run(self, context: ActionContext) -> ActionOutput:
        found, value = _mode(context)
        if found == OFFICIAL:
            return ActionOutput({CHUNKING_EXPERIMENT: None}, {"official": True, "skipped": "no chunking"})
        earlier = context.artifacts.get(CHUNKING_EXPERIMENT)
        if isinstance(earlier, str):  # the run was resumed after this stage started the experiment
            return self._resume(context, earlier)
        batch = ids(context, FILE_BATCH)
        if found == EXPERIMENT:
            return self._new(context, as_object(value, "experiment"), batch)
        return self._extend(context, str(value), batch)

    @staticmethod
    def _new(context: ActionContext, experiment: JsonObject, batch: list[str]) -> ActionOutput:
        if not batch:
            raise ActionError(f"{context.stage.id}: the batch is empty")
        served = _models(context)
        try:
            chunking = chunk_fit(as_object(experiment.get("chunking"), "chunking"), served)
        except InvalidRequest as e:
            raise ActionError(str(e)) from e
        name, description = experiment.get("name"), experiment.get("description")
        body: JsonObject = {
            "name": name if isinstance(name, str) and name.strip() else run_name(context),
            "description": description if isinstance(description, str) else f"pipeline {context.run.id}",
            "sha256s": json_list(batch),
            "chunking": chunking,
        }
        id = context.modules.chunking.start_experiment(body, context.watch)
        result: JsonObject = {"experiment": id, "documents": len(batch), "chunking": chunking}
        if served and str(chunking.get("chunker") or HYBRID) != HYBRID:
            result["warning"] = (
                f"{chunking.get('chunker')} chunks have no top: embeddings rejects a document with a chunk longer than"
                " a model's limit"
            )
        return ActionOutput({CHUNKING_EXPERIMENT: id}, result, id)

    @staticmethod
    def _extend(context: ActionContext, id: str, batch: list[str]) -> ActionOutput:
        info = context.modules.chunking.experiment_info(id)
        if info is None:
            raise ActionError(f"chunking has no experiment {id!r}")
        if info.status in ALIVE:
            raise ActionError(f"the chunking experiment {id} is {info.status}: resume the run when it ends")
        if not batch:
            return ActionOutput({CHUNKING_EXPERIMENT: id}, {"experiment": id, "added": 0, "skipped": "nothing new"})
        added = context.modules.chunking.add_documents(id, batch, context.watch)
        result: JsonObject = {
            "experiment": id,
            "added": added.added,
            "already": added.already,
            "unparsed": added.unparsed,
            "total": added.total,
        }
        return ActionOutput({CHUNKING_EXPERIMENT: id}, result, id)

    @staticmethod
    def _resume(context: ActionContext, id: str) -> ActionOutput:
        info = context.modules.chunking.experiment_info(id)
        if info is None:
            raise ActionError(f"chunking has no experiment {id!r} any more")
        resumed = info.status in CHUNKING_RESUMABLE
        if resumed:
            context.modules.chunking.resume_experiment(id, context.watch)
        result: JsonObject = {"experiment": id, "resumed": resumed, "status": info.status}
        return ActionOutput({CHUNKING_EXPERIMENT: id}, result, id)


class DataWaitExperiment(Action):
    name = "data.wait_experiment"
    kind = StageKind.TASK
    module = "data"
    needs = (CHUNKING_EXPERIMENT,)
    rewinds = True  # resumed, the run goes back to the stage that started the experiment (it resumes it)
    description = (
        "reads the chunking experiment in data (GET /data/nodes/EXPERIMENTO/{id}) until it ended: finished or"
        " partial go on (embeddings takes what was chunked), failed or interrupted stop the run (resume resumes it)"
    )

    def run(self, context: ActionContext) -> ActionOutput:
        experiment = context.artifacts.get(CHUNKING_EXPERIMENT)
        if not isinstance(experiment, str):
            return ActionOutput({}, {"skipped": "no chunking experiment to wait for (official)"})
        state = context.modules.data.wait_experiment(experiment, context.watch)
        if state.status not in CHUNKING_GOES_ON:
            raise ActionError(
                f"the chunking experiment {experiment} ended {state.status}: {state.error or 'no detail'}"
                " (resume the run to resume it)"
            )
        return ActionOutput({}, {"experiment": experiment, "status": state.status})


def _failed(context: ActionContext, failures: list[str]) -> ActionError:
    return ActionError(f"{context.stage.id}: {'; '.join(failures)} (resume the run to continue them)")


def _row(model: EmbeddingModel, action: str, outcome: JobOutcome) -> JsonObject:
    row: JsonObject = {"model": model.name, "action": action, "id": outcome.id, "status": outcome.status}
    if outcome.sha256s:
        row["embedded"] = len(outcome.sha256s)
    return row


def embed_official(context: ActionContext, served: list[EmbeddingModel]) -> ActionOutput:
    """The official chunks of the batch, an embeddings run per model (next to the active one); a model that fails
    doesn't stop the others, and the stage fails after them."""
    batch = ids(context, FILE_BATCH)
    rows: list[JsonValue] = []
    failures: list[str] = []
    embedded: set[str] | None = None
    for model in served:
        try:
            outcome = context.modules.embeddings.embed_model(batch, model.name, context.watch)
        except PipelineError as e:
            if context.watch.cancelled:
                raise
            failures.append(f"{model.name}: {e}")
            continue
        rows.append(_row(model, "embed", outcome))
        if not outcome.succeeded:
            failures.append(f"{model.name}: the run {outcome.id} ended {outcome.status}: {outcome.error or ''}")
            continue
        done = set(outcome.sha256s) if outcome.sha256s else set(batch)
        embedded = done if embedded is None else embedded & done
    if failures:
        raise _failed(context, failures)
    every = [s for s in batch if embedded is not None and s in embedded]
    return ActionOutput({EMBEDDINGS_EXPERIMENTS: [], EMBEDDED: json_list(every)}, {MODELS: rows, "official": True})


class EmbeddingsExperiments(Action):
    name = "embeddings.experiments"
    kind = StageKind.TASK
    module = "embeddings"
    needs = (CHUNKING_EXPERIMENT,)
    gives = (EMBEDDINGS_EXPERIMENTS, EMBEDDED)
    description = (
        "per model, in order: continues the embeddings experiment that chunking experiment already has of it (POST"
        " /embeddings/experiments/{id}/resume) or creates one (POST /embeddings/experiments), and waits; a model"
        " that fails doesn't stop the others (the stage fails after them: resume continues them). Official (no"
        " chunking experiment): an embeddings run per model over the batch's official chunks"
    )
    parameters = "models: [model, ...] (GET /embeddings/models; none: nothing is embedded)"

    def run(self, context: ActionContext) -> ActionOutput:
        served = _models(context)
        if not served:
            return ActionOutput({EMBEDDINGS_EXPERIMENTS: [], EMBEDDED: []}, {MODELS: [], "skipped": "no models"})
        experiment = context.artifacts.get(CHUNKING_EXPERIMENT)
        if experiment is None:
            return embed_official(context, served)
        if not isinstance(experiment, str):
            raise ActionError(f"{context.stage.id}: {CHUNKING_EXPERIMENT} isn't an id: {experiment!r}")
        info = context.modules.chunking.experiment_info(experiment)
        if info is None:
            raise ActionError(f"chunking has no experiment {experiment!r}")
        existing: dict[str, str] = {}
        for found in reversed(context.modules.embeddings.experiments_of(experiment)):  # the newest one wins
            existing[found.model] = found.id
        rows: list[JsonValue] = []
        made: list[str] = []
        failures: list[str] = []
        for model in served:
            action = "continue" if model.name in existing else "create"
            try:
                if model.name in existing:
                    outcome = context.modules.embeddings.resume(existing[model.name], context.watch)
                else:
                    body: JsonObject = {
                        "name": f"{run_name(context)} · {model.name}",
                        "description": f"pipeline {context.run.id}",
                        "chunking_experiment": experiment,
                        "model": model.name,
                        "max_tokens": embeddings_limit(info.chunking, model),
                    }
                    outcome = context.modules.embeddings.experiment(body, context.watch)
            except PipelineError as e:
                if context.watch.cancelled:
                    raise
                failures.append(f"{model.name}: {e}")
                continue
            rows.append(_row(model, action, outcome))
            made.append(outcome.id)
            if not outcome.succeeded:
                failures.append(f"{model.name}: {outcome.id} ended {outcome.status}: {outcome.error or 'no detail'}")
        if failures:
            raise _failed(context, failures)
        result: JsonObject = {"experiment": experiment, MODELS: rows}
        artifacts: JsonObject = {EMBEDDINGS_EXPERIMENTS: json_list(made), EMBEDDED: []}
        return ActionOutput(artifacts, result, embeddings_experiment=made[-1] if made else None)


class EmbeddingsEmbedModels(Action):
    name = "embeddings.embed_models"
    kind = StageKind.TASK
    module = "embeddings"
    needs = (FILE_BATCH,)
    gives = (EMBEDDED,)
    description = (
        "embeds the batch's official chunks with each model (POST /embeddings/runs {sha256s, model}), next to the"
        " active one, and waits; a model that fails doesn't stop the others"
    )
    parameters = "models: [model, ...] (GET /embeddings/models)"

    def run(self, context: ActionContext) -> ActionOutput:
        served = _models(context)
        if not served:
            return ActionOutput({EMBEDDED: []}, {MODELS: [], "skipped": "no models"})
        output = embed_official(context, served)
        return ActionOutput({EMBEDDED: output.artifacts[EMBEDDED]}, output.result)


__all__ = ["ChunkingExtend", "DataParsed", "DataWaitExperiment", "EmbeddingsEmbedModels", "EmbeddingsExperiments"]
