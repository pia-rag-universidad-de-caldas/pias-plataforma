"""The active configuration: the stored one if it still works, otherwise the default; and how PUT and PATCH change
it."""

from llm.config import DEFAULT_MODEL, MAX_TOKENS, NUM_CTX, SYSTEM, TEMPERATURE
from llm.models import ConfigOrigin, ConfigStore, InvalidChat, LlmConfig

from .validation import admitted, checked


def default_num_ctx(model: str) -> int:
    """NUM_CTX, never past what the model admits."""
    return min(NUM_CTX, admitted(model).context)


def default_config() -> LlmConfig:
    return LlmConfig(DEFAULT_MODEL, TEMPERATURE, default_num_ctx(DEFAULT_MODEL), MAX_TOKENS, SYSTEM)


def usable(config: LlmConfig | None) -> LlmConfig:
    """`config` if its model is still admitted and every value fits; otherwise the default."""
    if config is None:
        return default_config()
    try:
        return checked(config)
    except InvalidChat:
        return default_config()


def resolve(store: ConfigStore) -> LlmConfig:
    """The active configuration. DataDown goes through."""
    return usable(store.active())


def replaced(
    model: str,
    modified: str,
    temperature: float | None = None,
    num_ctx: int | None = None,
    max_tokens: int | None = None,
    system: str | None = None,
) -> LlmConfig:
    """PUT: what isn't given takes the default (num_ctx, the model's). InvalidChat if something doesn't fit."""
    return checked(
        LlmConfig(
            model,
            TEMPERATURE if temperature is None else temperature,
            default_num_ctx(model) if num_ctx is None else num_ctx,
            MAX_TOKENS if max_tokens is None else max_tokens,
            SYSTEM if system is None else system,
            ConfigOrigin.MANUAL,
            modified,
        )
    )


def patched(
    current: LlmConfig,
    modified: str,
    model: str | None = None,
    temperature: float | None = None,
    num_ctx: int | None = None,
    max_tokens: int | None = None,
    system: str | None = None,
) -> LlmConfig:
    """PATCH: only what is given changes. Another model keeps num_ctx if it still fits, otherwise takes its own."""
    chosen = model or current.model
    context = num_ctx
    if context is None:
        context = current.num_ctx if current.num_ctx <= admitted(chosen).context else default_num_ctx(chosen)
    return checked(
        LlmConfig(
            chosen,
            current.temperature if temperature is None else temperature,
            context,
            current.max_tokens if max_tokens is None else max_tokens,
            current.system if system is None else system,
            ConfigOrigin.MANUAL,
            modified,
        )
    )
