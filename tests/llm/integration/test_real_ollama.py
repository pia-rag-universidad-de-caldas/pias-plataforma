"""A real Ollama (`ollama` tests): only if OLLAMA_TEST_URL says where, and with the small model downloaded
(`ollama pull qwen2.5:0.5b`). Nothing is pulled nor deleted here."""

import os

import pytest

from llm.adapters import OllamaClient
from llm.domain import default_config, same_model, settle
from llm.models import ChatMessage, ChatRequest, Role

SMALL = "qwen2.5:0.5b"
URL = os.environ.get("OLLAMA_TEST_URL")

pytestmark = [
    pytest.mark.ollama,
    pytest.mark.integration,
    pytest.mark.skipif(not URL, reason="OLLAMA_TEST_URL is not set"),
]


@pytest.fixture
def ollama() -> OllamaClient:
    assert URL is not None
    client = OllamaClient(URL)
    if not any(same_model(SMALL, m.name) for m in client.installed()):
        client.close()
        pytest.skip(f"Ollama hasn't downloaded {SMALL}: ollama pull {SMALL}")
    return client


def test_a_real_chat_answers_text_and_counts_tokens(ollama: OllamaClient) -> None:
    question = ChatRequest((ChatMessage(Role.USER, "Responde solo con la palabra: hola"),), SMALL, 0.0, 2048, 16)
    with ollama:
        answer = ollama.chat(settle(default_config(), question))
    assert answer.content.strip() and answer.prompt_tokens > 0 and answer.answer_tokens > 0 and answer.seconds > 0
