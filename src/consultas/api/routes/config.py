"""The active configuration: GET/PUT/PATCH/DELETE /config (CONFIG_OFICIAL/consultas). How many chunks are searched
(`k`), the least score of one that goes as context (`min_score`), the prompt (with {context} and {question}) and how
many previous turns of a chat go to the LLM (`history`). Without one set, config.py's."""

from fastapi import APIRouter

from common.clock import now
from consultas.api.dependencies import Config
from consultas.api.responses import DOWN, INVALID
from consultas.api.schemas import ConfigBody, ConfigPatch, ConfigView, DefaultConfig
from consultas.domain import checked, default_config, usable
from consultas.models import ConfigOrigin, ConsultasConfig

router = APIRouter(prefix="/config", tags=["config"])


def config_view(stored: ConsultasConfig | None) -> ConfigView:
    used, default = usable(stored), default_config()
    problem = None
    if stored is not None and used != stored:
        problem = "the stored configuration can't be used (a value out of range, no prompt marks): the default applies"
    return ConfigView(
        used.k,
        used.min_score,
        used.prompt,
        used.history,
        used.origin,
        used.modified,
        problem,
        DefaultConfig(default.k, default.min_score, default.prompt, default.history),
    )


def _set(config: Config, base: ConsultasConfig, body: ConfigBody | ConfigPatch) -> ConfigView:
    active = checked(  # 422 before anything is written
        ConsultasConfig(
            body.k if body.k is not None else base.k,
            body.min_score if body.min_score is not None else base.min_score,
            body.prompt if body.prompt is not None else base.prompt,
            body.history if body.history is not None else base.history,
            ConfigOrigin.MANUAL,
            now(),
        )
    )
    config.set(active)
    return config_view(active)


@router.get("", responses=DOWN)
def read_config(config: Config) -> ConfigView:
    """The active configuration, where it came from and the default."""
    return config_view(config.active())


@router.put("", responses=DOWN | INVALID)
def replace_config(config: Config, body: ConfigBody) -> ConfigView:
    """Sets it by hand; what is left out takes the default."""
    return _set(config, default_config(), body)


@router.patch("", responses=DOWN | INVALID)
def change_config(config: Config, body: ConfigPatch) -> ConfigView:
    """Changes only what comes."""
    return _set(config, usable(config.active()), body)


@router.delete("", responses=DOWN)
def reset_config(config: Config) -> ConfigView:
    """Back to the default."""
    config.clear()
    return config_view(None)
