"""The laboratory's pair (feature 044): one iteration tries a chunking configuration and an embeddings model together,
so the pipeline makes them fit before launching anything.

    chunking.tokenizer  = embeddings.model (the chunks are counted with the model's own tokenizer)
    chunking.max_tokens <= model limit - SPECIAL_TOKENS (the limit counts [CLS] and [SEP]; chunking doesn't);
                          if not given (hybrid), the model's default - SPECIAL_TOKENS
    embeddings.max_tokens = chunking.max_tokens + SPECIAL_TOKENS (the model's limit, for the other chunkers)

Neither chunking nor embeddings knows about the other: only the pipeline, which joins them, checks this.

Feature 050 makes it a trio: an iteration may also say the `llm` that answers over its chunks
({model, temperature, num_ctx, max_tokens, system}); its model must be admitted by llm and downloaded. Without `llm`,
nothing of this is asked of llm.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from pipeline.config import SPECIAL_TOKENS
from pipeline.models import EmbeddingModel, InvalidRequest, JsonObject, JsonValue, LlmModel, Stage, as_object

from .merge import deep_merge

HYBRID = "hybrid"  # chunking's default chunker, the only one with max_tokens
EXPERIMENT_ACTION = "chunking.experiment"  # a cycle with this step is a laboratory cycle
LLM = "llm"  # the key of an iteration's llm configuration
LLM_KEYS = ("model", "temperature", "num_ctx", "max_tokens", "system")  # what PUT /llm/config takes


@dataclass(frozen=True)
class Pair:
    chunking: JsonObject  # the `chunking` of POST /chunking/experiments
    embeddings: JsonObject  # the model and max_tokens of the embeddings experiment


def _model(asked: object, models: Sequence[EmbeddingModel]) -> EmbeddingModel:
    if not models:
        raise InvalidRequest("embeddings admits no model")
    if asked is None:
        defaults = [m for m in models if m.default] or (list(models) if len(models) == 1 else [])
        if not defaults:
            raise InvalidRequest(f"say embeddings.model: one of {[m.name for m in models]}")
        return defaults[0]
    found = next((m for m in models if m.name == asked), None)
    if found is None:
        raise InvalidRequest(f"embeddings.model {asked!r} isn't admitted; admitted: {[m.name for m in models]}")
    return found


def pair(config: JsonObject, models: Sequence[EmbeddingModel]) -> Pair:
    """The chunking and embeddings configurations of an iteration, made to fit; InvalidRequest if they can't."""
    chunking = dict(as_object(config.get("chunking"), "chunking"))
    embeddings = dict(as_object(config.get("embeddings"), "embeddings"))
    model = _model(embeddings.get("model"), models)
    tokenizer = chunking.get("tokenizer")
    if tokenizer is not None and tokenizer != model.name:
        raise InvalidRequest(f"chunking.tokenizer must be the embeddings model ({model.name}), not {tokenizer!r}")
    chunking["tokenizer"] = model.name
    limit = model.max_tokens - SPECIAL_TOKENS
    if str(chunking.get("chunker") or HYBRID) == HYBRID:
        asked = chunking.get("max_tokens")
        if asked is None:
            asked = model.default_tokens - SPECIAL_TOKENS
        if isinstance(asked, bool) or not isinstance(asked, int) or asked < 1:
            raise InvalidRequest(f"chunking.max_tokens must be a positive integer, not {asked!r}")
        if asked > limit:
            raise InvalidRequest(
                f"chunking.max_tokens ({asked}) can't pass {limit}: the limit of {model.name} ({model.max_tokens})"
                f" minus its {SPECIAL_TOKENS} special tokens"
            )
        chunking["max_tokens"] = asked
        tokens = asked + SPECIAL_TOKENS
    else:  # hierarchical and page chunks have no top: the embeddings cut them at the model's limit
        tokens = model.max_tokens
    given = embeddings.get("max_tokens")
    if given is not None and given != tokens:
        raise InvalidRequest(
            f"embeddings.max_tokens is chunking.max_tokens + {SPECIAL_TOKENS} ({tokens}): leave it out"
        )
    embeddings.update({"model": model.name, "max_tokens": tokens})
    return Pair(chunking, embeddings)


def _positive(value: JsonValue, where: str) -> None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 1):
        raise InvalidRequest(f"{where} must be a positive integer, not {value!r}")


def fit_llm(config: JsonObject, models: Sequence[LlmModel]) -> JsonObject | None:
    """The iteration's llm configuration, checked against llm's models (InvalidRequest, 422, if it can't be used);
    None if the iteration has none."""
    if config.get(LLM) is None:
        return None
    llm = as_object(config.get(LLM), LLM)
    unknown = sorted(set(llm) - set(LLM_KEYS))
    if unknown:
        raise InvalidRequest(f"llm doesn't take {unknown}; it takes {list(LLM_KEYS)}")
    admitted = [m.name for m in models]
    name = llm.get("model")
    if not isinstance(name, str) or not name:
        raise InvalidRequest(f"say llm.model: one of {admitted}")
    model = next((m for m in models if m.name == name), None)
    if model is None:
        raise InvalidRequest(f"llm.model {name!r} isn't admitted; admitted: {admitted}")
    if not model.installed:
        raise InvalidRequest(f"llm.model {name!r} isn't downloaded: pull it first (POST /llm/models/pull)")
    temperature = llm.get("temperature")
    if temperature is not None and (
        isinstance(temperature, bool) or not isinstance(temperature, int | float) or temperature < 0
    ):
        raise InvalidRequest(f"llm.temperature must be a number of at least 0, not {temperature!r}")
    _positive(llm.get("num_ctx"), "llm.num_ctx")
    _positive(llm.get("max_tokens"), "llm.max_tokens")
    num_ctx = llm.get("num_ctx")
    if isinstance(num_ctx, int) and model.context is not None and num_ctx > model.context:
        raise InvalidRequest(f"llm.num_ctx ({num_ctx}) can't pass the context of {name} ({model.context})")
    system = llm.get("system")
    if system is not None and not isinstance(system, str):
        raise InvalidRequest(f"llm.system must be a text, not {system!r}")
    return llm


def fit(config: JsonObject, models: Sequence[EmbeddingModel], llm_models: Callable[[], Sequence[LlmModel]]) -> None:
    """InvalidRequest (422) if an iteration's configuration can't run: its pair doesn't fit or its llm can't be used.
    `llm_models` is only asked when the iteration has an llm."""
    pair(config, models)
    if config.get(LLM) is not None:
        fit_llm(config, llm_models())


def lab_cycles(stages: Sequence[Stage]) -> list[Stage]:
    """The cycles that try a chunking + embeddings pair (and an llm, if they say one)."""
    return [s for s in stages if s.is_cycle and any(step.action == EXPERIMENT_ACTION for step in s.stages)]


def check_cycles(
    stages: Sequence[Stage],
    params: dict[str, JsonObject],
    models: Sequence[EmbeddingModel],
    llm_models: Callable[[], Sequence[LlmModel]] = list,
) -> None:
    """Before a run starts: each laboratory cycle's first configuration fits (InvalidRequest, 422, if not)."""
    for cycle in lab_cycles(stages):
        fit(deep_merge(cycle.params, params.get(cycle.id, {})), models, llm_models)
