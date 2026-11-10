"""The active configuration: the stored one if it still works, otherwise the default."""

from embeddings.config import DEFAULT_MODEL, MODELS
from embeddings.models import ConfigOrigin, ConfigStore, EmbeddingConfig, InvalidLimit

from .limits import token_limit


def default_config() -> EmbeddingConfig:
    return EmbeddingConfig(DEFAULT_MODEL, MODELS[DEFAULT_MODEL].default_tokens)


def usable(config: EmbeddingConfig | None) -> EmbeddingConfig:
    """`config` if its model is still served and its limit fits; otherwise the default."""
    if config is None:
        return default_config()
    try:
        token_limit(config.model, config.max_tokens)
    except InvalidLimit:
        return default_config()
    return config


def resolve(store: ConfigStore) -> EmbeddingConfig:
    """The active configuration. UpstreamDown (data down) goes through."""
    return usable(store.active())


def run_config(active: EmbeddingConfig, model: str | None) -> EmbeddingConfig:
    """What a production run uses (feature 055): the active configuration, or another served model next to it (with
    its default limit) to change models without cutting the chat. InvalidLimit (422) if that model isn't served."""
    if model is None or model == active.model:
        return active
    return EmbeddingConfig(model, token_limit(model, None), ConfigOrigin.MANUAL)
