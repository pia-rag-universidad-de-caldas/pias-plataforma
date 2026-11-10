"""The active configuration: GET/PUT/PATCH/DELETE /config (CONFIG_OFICIAL/llm in data). What POST /chat uses for
what it doesn't send: the one someone set or, if nobody did (or its model is no longer admitted), the default. A model
may be set before Ollama has it: the chat then answers 503 with the `ollama pull` that fixes it."""

from fastapi import APIRouter

from common.clock import now
from llm.api.dependencies import Config
from llm.api.responses import DATA_DOWN, INVALID, REFUSED
from llm.api.schemas import ConfigBody, ConfigPatch, ConfigView, DefaultConfig
from llm.domain import default_config, patched, replaced, resolve
from llm.models import LlmConfig

router = APIRouter(prefix="/config", tags=["config"])


def config_view(used: LlmConfig) -> ConfigView:
    default = default_config()
    return ConfigView(
        used.model,
        used.temperature,
        used.num_ctx,
        used.max_tokens,
        used.system,
        used.origin,
        used.modified,
        DefaultConfig(default.model, default.temperature, default.num_ctx, default.max_tokens, default.system),
    )


def _set(config: Config, active: LlmConfig) -> ConfigView:
    config.set(active)
    return config_view(active)


@router.get("", responses=DATA_DOWN)
def read_config(config: Config) -> ConfigView:
    """The active configuration, where it came from, and the default."""
    return config_view(resolve(config))


@router.put("", responses=DATA_DOWN | INVALID | REFUSED)
def replace_config(config: Config, body: ConfigBody) -> ConfigView:
    """Sets it by hand; what is left out takes the default (num_ctx: the model's)."""
    active = replaced(body.model, now(), body.temperature, body.num_ctx, body.max_tokens, body.system)  # 422 first
    return _set(config, active)


@router.patch("", responses=DATA_DOWN | INVALID | REFUSED)
def change_config(config: Config, body: ConfigPatch) -> ConfigView:
    """Changes only what comes. Another model keeps num_ctx if it fits, otherwise takes its own."""
    current = resolve(config)
    changed = patched(current, now(), body.model, body.temperature, body.num_ctx, body.max_tokens, body.system)
    return _set(config, changed)


@router.delete("", responses=DATA_DOWN)
def reset_config(config: Config) -> ConfigView:
    """Back to the default."""
    config.clear()
    return config_view(default_config())
