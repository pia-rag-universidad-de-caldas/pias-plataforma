"""data's CONFIG_OFICIAL/llm as this module's configuration, and back: the only place where the names stored in Spanish
become models."""

from collections.abc import Mapping

from common.clock import now
from common.http import Json
from llm.models import ConfigOrigin, ConfigProperties, LlmConfig


def _text(raw: Mapping[str, Json], key: str) -> str | None:
    value = raw.get(key)
    return value if isinstance(value, str) else None


def _integer(raw: Mapping[str, Json], key: str) -> int | None:
    value = raw.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _number(raw: Mapping[str, Json], key: str) -> float | None:
    value = raw.get(key)
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def config(raw: Mapping[str, Json]) -> LlmConfig | None:
    """None if it can't be read (then the default applies)."""
    model, temperature = _text(raw, "modelo"), _number(raw, "temperatura")
    num_ctx, max_tokens = _integer(raw, "num_ctx"), _integer(raw, "max_tokens")
    if model is None or temperature is None or num_ctx is None or max_tokens is None:
        return None
    origin = _text(raw, "origen")
    known = {o.value for o in ConfigOrigin}
    return LlmConfig(
        model,
        temperature,
        num_ctx,
        max_tokens,
        _text(raw, "sistema") or "",
        ConfigOrigin(origin) if origin in known else ConfigOrigin.MANUAL,
        _text(raw, "modificado_en"),
    )


def config_properties(config: LlmConfig) -> ConfigProperties:
    return {
        "modulo": "llm",
        "modelo": config.model,
        "temperatura": config.temperature,
        "num_ctx": config.num_ctx,
        "max_tokens": config.max_tokens,
        "sistema": config.system,
        "origen": config.origin.value,
        "modificado_en": config.modified or now(),
    }
