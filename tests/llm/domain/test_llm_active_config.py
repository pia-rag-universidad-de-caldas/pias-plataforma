"""The active configuration: the stored one if it still works, else the default; PUT and PATCH on it."""

import pytest

from llm.config import DEFAULT_MODEL, MAX_TOKENS, MODELS, NUM_CTX, TEMPERATURE
from llm.domain import canonical, default_config, patched, replaced, same_model, usable
from llm.models import ConfigOrigin, InvalidChat, LlmConfig

AT = "2026-11-10T10:00:00+00:00"


def test_the_default_is_the_default_model_with_the_default_values() -> None:
    config = default_config()
    assert (config.model, config.temperature, config.max_tokens) == (DEFAULT_MODEL, TEMPERATURE, MAX_TOKENS)
    assert config.num_ctx == min(NUM_CTX, MODELS[DEFAULT_MODEL].context) and config.origin is ConfigOrigin.DEFAULT
    assert DEFAULT_MODEL in MODELS


@pytest.mark.parametrize(
    "stored",
    [None, LlmConfig("gone:1b", 0.2, 4096, 100, ""), LlmConfig("qwen2.5:0.5b", 9.0, 4096, 100, "")],
    ids=["none", "model no longer admitted", "out of range"],
)
def test_a_stored_one_that_does_not_work_gives_the_default(stored: LlmConfig | None) -> None:
    assert usable(stored) == default_config()


def test_a_stored_one_that_works_is_used() -> None:
    stored = LlmConfig("qwen2.5:0.5b", 0.7, 2048, 100, "x", ConfigOrigin.MANUAL, AT)
    assert usable(stored) == stored


def test_put_fills_what_is_missing_with_the_defaults() -> None:
    config = replaced("qwen2.5:0.5b", AT, system="s")
    assert (config.temperature, config.num_ctx, config.max_tokens, config.system) == (
        TEMPERATURE,
        NUM_CTX,
        MAX_TOKENS,
        "s",
    )
    assert (config.origin, config.modified) == (ConfigOrigin.MANUAL, AT)
    with pytest.raises(InvalidChat):
        replaced("qwen2.5:0.5b", AT, num_ctx=10**6)


def test_patch_keeps_the_rest_and_another_model_keeps_num_ctx_only_if_it_fits() -> None:
    current = LlmConfig("llama3.1:8b", 0.5, 100_000, 300, "s")
    changed = patched(current, AT, temperature=0.1)
    assert (changed.model, changed.temperature, changed.num_ctx, changed.system) == ("llama3.1:8b", 0.1, 100_000, "s")
    small = patched(current, AT, model="qwen2.5:0.5b")
    assert small.num_ctx == NUM_CTX and small.max_tokens == 300
    with pytest.raises(InvalidChat):
        patched(current, AT, model="nope")


def test_a_name_without_tag_is_latest() -> None:
    assert canonical("llama3.1") == "llama3.1:latest" and canonical("hf.co/a/b:q4") == "hf.co/a/b:q4"
    assert same_model("llama3.1", "llama3.1:latest") and not same_model("llama3.1:8b", "llama3.1:latest")
