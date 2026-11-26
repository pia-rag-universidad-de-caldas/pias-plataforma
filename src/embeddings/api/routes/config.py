"""The active configuration: GET/PUT/PATCH/DELETE /config. What POST /runs and POST /vectors use: the one someone set
(by hand, or with POST /experiments/{id}/apply) or, if nobody did, the default model with its default limit. Changing
it embeds nothing: a chunk that fit is embedded the same with any limit that holds it, so only the documents that
failed for being too long are tried again; another model is another index, and every document is embedded again."""

from fastapi import APIRouter

from common.clock import now
from embeddings.api.dependencies import Config
from embeddings.api.responses import DOWN, INVALID
from embeddings.api.schemas import ConfigBody, ConfigPatch, ConfigView, DefaultConfig
from embeddings.domain import default_config, token_limit, usable, vector_property
from embeddings.models import ConfigOrigin, EmbeddingConfig

router = APIRouter(prefix="/config", tags=["config"])


def config_view(stored: EmbeddingConfig | None) -> ConfigView:
    used, default = usable(stored), default_config()
    problem = None
    if stored is not None and used != stored:
        problem = f"the stored configuration ({stored.model}, {stored.max_tokens}) can't be used: the default applies"
    return ConfigView(
        used.model,
        used.max_tokens,
        used.origin,
        used.experiment,
        used.modified,
        problem,
        DefaultConfig(default.model, default.max_tokens),
        vector_property(used.model),
    )


def _set(config: Config, model: str, max_tokens: int | None) -> ConfigView:
    active = EmbeddingConfig(model, token_limit(model, max_tokens), ConfigOrigin.MANUAL, None, now())  # 422 first
    config.set(active)
    return config_view(active)


@router.get("", responses=DOWN)
def read_config(config: Config) -> ConfigView:
    """The active configuration and where it came from."""
    return config_view(config.active())


@router.put("", responses=DOWN | INVALID)
def replace_config(config: Config, body: ConfigBody) -> ConfigView:
    """Sets the model and its limit by hand; without max_tokens, the model's default."""
    return _set(config, body.model, body.max_tokens)


@router.patch("", responses=DOWN | INVALID)
def change_config(config: Config, body: ConfigPatch) -> ConfigView:
    """Changes only what comes. Another model without max_tokens takes its default limit."""
    current = usable(config.active())
    model = body.model or current.model
    limit = body.max_tokens if body.max_tokens is not None else (current.max_tokens if model == current.model else None)
    return _set(config, model, limit)


@router.delete("", responses=DOWN)
def reset_config(config: Config) -> ConfigView:
    """Back to the default."""
    config.clear()
    return config_view(None)
