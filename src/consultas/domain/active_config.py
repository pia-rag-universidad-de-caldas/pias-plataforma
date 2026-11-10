"""The active configuration: the stored one if it still works, otherwise the default (config.py)."""

from consultas.config import CONTEXT_MARK, HISTORY, MAX_HISTORY, MAX_K, MAX_PROMPT, MIN_SCORE, PROMPT, QUESTION_MARK, K
from consultas.models import ConfigStore, ConsultasConfig, InvalidQuestion


def default_config() -> ConsultasConfig:
    return ConsultasConfig(K, MIN_SCORE, PROMPT, HISTORY)


def config_problems(config: ConsultasConfig) -> list[str]:
    """Everything wrong with a configuration; empty if it can be used."""
    problems: list[str] = []
    if not 1 <= config.k <= MAX_K:
        problems.append(f"k must be between 1 and {MAX_K}")
    if not 0.0 <= config.min_score <= 1.0:
        problems.append("min_score must be between 0 and 1 (cosine)")
    if not 0 <= config.history <= MAX_HISTORY:
        problems.append(f"history must be between 0 and {MAX_HISTORY}")
    if len(config.prompt) > MAX_PROMPT:
        problems.append(f"the prompt has more than {MAX_PROMPT} characters")
    missing = [mark for mark in (CONTEXT_MARK, QUESTION_MARK) if mark not in config.prompt]
    if missing:
        problems.append(f"the prompt must have {' and '.join(missing)}")
    return problems


def checked(config: ConsultasConfig) -> ConsultasConfig:
    """`config`, or InvalidQuestion (422) with what is wrong."""
    problems = config_problems(config)
    if problems:
        raise InvalidQuestion("; ".join(problems))
    return config


def usable(config: ConsultasConfig | None) -> ConsultasConfig:
    """`config` if it can be used; otherwise the default (a stored one from another version, edited by hand...)."""
    if config is None or config_problems(config):
        return default_config()
    return config


def resolve(store: ConfigStore) -> ConsultasConfig:
    """The active configuration. DataDown goes through."""
    return usable(store.active())
