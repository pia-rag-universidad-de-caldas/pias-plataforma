"""The experiments pipeline (feature 062), without I/O of its own: what a run's params say and the checks before it
starts.

    seleccionar (data.parsed)            the parsed documents of the selection (official: the officially chunked);
                                         with `extend`, without those the experiment has
    chunkear (chunking.extend)           params: exactly one of
                                           experiment: {name?, description?, chunking}   a new chunking experiment
                                           extend: "<id>"                                 add to that one
                                           official: true                                 no chunking: official chunks
    esperar_chunking (data.wait_experiment)   data says when the experiment ended
    embeber (embeddings.experiments)     params: models: [...]: per model, a new embeddings experiment or the one it
                                         has continued; official: an embeddings run per model

The pipeline chooses (with what data answers); chunking and embeddings get explicit lists (rule of feature 042).
"""

from collections.abc import Sequence

from pipeline.config import CHUNKED_UNIVERSE, PARSED_UNIVERSE
from pipeline.models import (
    ConflictError,
    InvalidRequest,
    JsonObject,
    JsonValue,
    Modules,
    NotFoundError,
    Stage,
    as_object,
    json_list,
)

from .merge import deep_merge
from .pairing import chosen_models, chunk_fit, uncovered

SELECT_ACTION = "data.parsed"
CHUNK_ACTION = "chunking.extend"
EMBED_ACTIONS = frozenset({"embeddings.experiments", "embeddings.embed_models"})
EXPERIMENT, EXTEND, OFFICIAL = "experiment", "extend", "official"
MODES = (EXPERIMENT, EXTEND, OFFICIAL)
MODELS = "models"  # the key of the embedding models, in the embeddings stage (and copied to the chunking one)
UNIVERSE = "universe"
EXCLUDE = "exclude_experiment"
_EXPERIMENT_KEYS = frozenset({"name", "description", "chunking"})
ALIVE = frozenset({"queued", "running"})  # a chunking experiment that can't take documents now


def _config(stage: Stage, params: dict[str, JsonObject]) -> JsonObject:
    return deep_merge(stage.params, params.get(stage.id, {}))


def mode(config: JsonObject, where: str = "chunkear") -> tuple[str, JsonValue]:
    """(mode, its value) of a chunking stage's params; InvalidRequest (422) unless exactly one is there."""
    given = [m for m in MODES if config.get(m) not in (None, False)]
    if len(given) != 1:
        raise InvalidRequest(f"params.{where}: exactly one of {list(MODES)}")
    found = given[0]
    value = config[found]
    if found == OFFICIAL and value is not True:
        raise InvalidRequest(f"params.{where}.official must be true")
    if found == EXTEND and (not isinstance(value, str) or not value.strip()):
        raise InvalidRequest(f"params.{where}.extend must be the id of a chunking experiment")
    if found == EXPERIMENT:
        experiment = as_object(value, f"params.{where}.experiment")
        unknown = sorted(set(experiment) - _EXPERIMENT_KEYS)
        if unknown:
            raise InvalidRequest(
                f"params.{where}.experiment: unknown keys {unknown} (allowed: {sorted(_EXPERIMENT_KEYS)})"
            )
        for key in ("name", "description"):
            if experiment.get(key) is not None and not isinstance(experiment[key], str):
                raise InvalidRequest(f"params.{where}.experiment.{key} must be a text")
        as_object(experiment.get("chunking"), f"params.{where}.experiment.chunking")
    return found, value


def models(config: JsonObject, where: str = "embeber") -> list[str]:
    """The embedding models of a stage's params (none: nothing is embedded); InvalidRequest if malformed."""
    value = config.get(MODELS)
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(m, str) and m.strip() for m in value):
        raise InvalidRequest(f"params.{where}.models must be a list of model names")
    names = [str(m) for m in value]
    repeated = sorted({m for m in names if names.count(m) > 1})
    if repeated:
        raise InvalidRequest(f"params.{where}.models repeats {repeated}")
    return names


def _stages(stages: Sequence[Stage], actions: frozenset[str]) -> list[Stage]:
    return [s for s in stages if not s.is_cycle and s.action in actions]


def is_experiments(stages: Sequence[Stage]) -> bool:
    """Whether the template chunks with chunking.extend (the experiments pipeline)."""
    return bool(_stages(stages, frozenset({CHUNK_ACTION})))


def prepared(stages: Sequence[Stage], params: dict[str, JsonObject]) -> dict[str, JsonObject]:
    """`params` of an experiments run with what each stage needs of the others: the selection's universe (official:
    the officially chunked) and the experiment whose documents it leaves out (extend), and the models the chunks are
    made for. InvalidRequest (422) for a malformed mode or list of models. Any other template, unchanged."""
    chunkers = _stages(stages, frozenset({CHUNK_ACTION}))
    if not chunkers:
        return params
    changed = dict(params)
    names: list[str] = []
    for stage in _stages(stages, EMBED_ACTIONS):
        names = names or models(_config(stage, params), stage.id)
    for stage in chunkers:
        found, value = mode(_config(stage, params), stage.id)
        changed[stage.id] = deep_merge(changed.get(stage.id, {}), {MODELS: json_list(names)})
        selection: JsonObject = {UNIVERSE: CHUNKED_UNIVERSE if found == OFFICIAL else PARSED_UNIVERSE}
        if found == EXTEND:
            selection[EXCLUDE] = value
        for select in _stages(stages, frozenset({SELECT_ACTION})):
            changed[select.id] = deep_merge(selection, changed.get(select.id, {}))
    return changed


def check(stages: Sequence[Stage], params: dict[str, JsonObject], modules: Modules) -> None:
    """Before an experiments run starts (feature 062): each model is served and fits the chunks (a new experiment's
    `fit`, the extended experiment's parameters or the active configuration). InvalidRequest (422) with the model
    that doesn't fit, NotFoundError (404) for an experiment chunking doesn't have, ConflictError (409) for one in line
    or running."""
    for stage in _stages(stages, frozenset({CHUNK_ACTION})):
        config = _config(stage, params)
        found, value = mode(config, stage.id)
        names = models(config, stage.id)
        served = chosen_models(names, modules.embeddings.models()) if names else []
        if found == EXPERIMENT:
            experiment = as_object(value, f"params.{stage.id}.experiment")
            chunk_fit(as_object(experiment.get("chunking"), "chunking"), served)
            continue
        if found == EXTEND:
            info = modules.chunking.experiment_info(str(value))
            if info is None:
                raise NotFoundError(f"chunking has no experiment {value!r}")
            if info.status in ALIVE:
                raise ConflictError(f"the chunking experiment {value} is {info.status}: wait until it ends")
            chunking, what = info.chunking, f"the chunks of the experiment {value}"
        else:
            active = modules.chunking.config()
            if active is None:
                raise InvalidRequest("chunking has no active configuration: the official chunks can't be embedded")
            chunking, what = active, "the official chunks"
        problems = uncovered(chunking, served, official=found == OFFICIAL)
        if problems:
            hint = "a new experiment is needed" if found == EXTEND else "chunk them with a fit for those models"
            raise InvalidRequest(f"{what}: {'; '.join(problems)} ({hint})")


def plan(
    stages: Sequence[Stage], params: dict[str, JsonObject], files: JsonObject, batch: Sequence[str], modules: Modules
) -> JsonObject:
    """What an experiments run would do (simulate): how many documents enter, how many the extended experiment
    already had (of those the same filters take; `files`: the selection as data takes it) and, per model, whether it
    creates an embeddings experiment, continues the one it has, or embeds the official chunks."""
    summary: JsonObject = {"documents": len(batch)}
    for stage in _stages(stages, frozenset({CHUNK_ACTION})):
        config = _config(stage, params)
        found, value = mode(config, stage.id)
        summary["mode"] = found
        names = models(config, stage.id)
        existing: dict[str, str] = {}
        if found == EXTEND:
            summary["experiment"] = value
            summary["already"] = _already(files, str(value), modules)
            for info in reversed(modules.embeddings.experiments_of(str(value))):  # the newest one wins
                existing[info.model] = info.id
        rows: list[JsonValue] = []
        for name in names:
            if found == OFFICIAL:
                rows.append({"model": name, "action": "embed"})
            elif name in existing:
                rows.append({"model": name, "action": "continue", "experiment": existing[name]})
            else:
                rows.append({"model": name, "action": "create"})
        summary[MODELS] = rows
    return summary


def unpaged(files: JsonObject) -> JsonObject:
    """The same selection without its page or sample: every document its filters (or its sha256s) take."""
    if "sha256s" in files:
        return {"sha256s": files["sha256s"]}
    kept = {k: v for k, v in files.items() if k not in ("all", "sample", "seed", "pages", "per_page")}
    return {"all": True, **kept}


def _already(files: JsonObject, experiment: str, modules: Modules) -> int:
    """How many documents of the selection's filters the experiment has: those they take minus the new ones."""
    every = unpaged(files)
    total = modules.data.select(PARSED_UNIVERSE, every, None, 1, 1).total
    new = modules.data.select(PARSED_UNIVERSE, every, experiment, 1, 1).total
    return max(0, total - new)
