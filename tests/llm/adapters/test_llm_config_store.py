"""The active configuration over data (FakeData): CONFIG_OFICIAL/llm, written with merge, read back as it was."""

import httpx
import pytest
from fakes import FakeData

from llm.adapters import HttpSession
from llm.models import ConfigOrigin, DataDown, LlmConfig

CONFIG = LlmConfig("qwen2.5:0.5b", 0.4, 2048, 128, "Sé breve.", ConfigOrigin.MANUAL, "2026-11-10T10:00:00+00:00")


def session(data: FakeData) -> HttpSession:
    return HttpSession("http://server", transport=httpx.MockTransport(data.handle))


def test_set_read_and_clear(fake_data: FakeData) -> None:
    with session(fake_data) as s:
        assert s.config.active() is None
        s.config.set(CONFIG)
        assert s.config.active() == CONFIG
        assert s.config.clear() is True and s.config.clear() is False
    nodes = fake_data.batches[0]["nodes"]
    assert isinstance(nodes, list)
    node = nodes[0]
    assert (node["label"], node["id"], node["mode"]) == ("CONFIG_OFICIAL", "llm", "merge")
    assert node["properties"] == {
        "modulo": "llm",
        "modelo": "qwen2.5:0.5b",
        "temperatura": 0.4,
        "num_ctx": 2048,
        "max_tokens": 128,
        "sistema": "Sé breve.",
        "origen": "manual",
        "modificado_en": "2026-11-10T10:00:00+00:00",
    }


def test_a_node_that_cannot_be_read_is_none(fake_data: FakeData) -> None:
    fake_data.nodes[("CONFIG_OFICIAL", "llm")] = {"modelo": "qwen2.5:0.5b"}
    with session(fake_data) as s:
        assert s.config.active() is None


def test_data_down(fake_data: FakeData) -> None:
    fake_data.down = True
    with session(fake_data) as s, pytest.raises(DataDown):
        s.config.active()
