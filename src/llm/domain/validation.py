"""What a value must be to reach Ollama: an admitted model, and every number inside its range."""

from llm.config import MAX_TOKENS_RANGE, MIN_NUM_CTX, MODELS, TEMPERATURE_RANGE, ModelSpec
from llm.models import InvalidChat, LlmConfig


def admitted(model: str) -> ModelSpec:
    """InvalidChat if the project doesn't admit it (config.MODELS), even if Ollama has it."""
    spec = MODELS.get(model)
    if spec is None:
        raise InvalidChat(f"the model {model!r} isn't admitted; admitted: {sorted(MODELS)}")
    return spec


def _within(name: str, value: float, low: float, high: float, model: str = "") -> None:
    if not low <= value <= high:
        which = f" for {model}" if model else ""
        raise InvalidChat(f"{name} must be between {low} and {high}{which}, not {value}")


def check_values(model: str, temperature: float, num_ctx: int, max_tokens: int) -> None:
    """InvalidChat with the first value that doesn't fit."""
    spec = admitted(model)
    _within("temperature", temperature, *TEMPERATURE_RANGE)
    _within("num_ctx", num_ctx, MIN_NUM_CTX, spec.context, model)
    _within("max_tokens", max_tokens, *MAX_TOKENS_RANGE)


def checked(config: LlmConfig) -> LlmConfig:
    check_values(config.model, config.temperature, config.num_ctx, config.max_tokens)
    return config
