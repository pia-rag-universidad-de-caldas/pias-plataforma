"""settle: a chat on the active configuration, checked before Ollama is asked."""

import pytest

from llm.config import MAX_IMAGES, MODELS
from llm.domain import default_config, settle
from llm.models import ChatMessage, ChatRequest, InvalidChat, LlmConfig, Role

HELLO = (ChatMessage(Role.USER, "hola"),)
IMAGE = "aGVsbG8="  # base64 of "hello"
CONFIG = LlmConfig("qwen2.5:0.5b", 0.3, 4096, 200, "Responde breve.")


def test_what_is_not_sent_comes_from_the_configuration() -> None:
    settled = settle(CONFIG, ChatRequest(HELLO))
    assert (settled.model, settled.temperature, settled.num_ctx, settled.max_tokens) == ("qwen2.5:0.5b", 0.3, 4096, 200)


def test_what_is_sent_wins() -> None:
    settled = settle(CONFIG, ChatRequest(HELLO, "llama3.1:8b", 0.0, 1024, 50))
    assert (settled.model, settled.temperature, settled.num_ctx, settled.max_tokens) == ("llama3.1:8b", 0.0, 1024, 50)


def test_the_system_prompt_goes_first_only_if_the_messages_bring_none() -> None:
    assert settle(CONFIG, ChatRequest(HELLO)).messages == (ChatMessage(Role.SYSTEM, "Responde breve."), *HELLO)
    own = (ChatMessage(Role.SYSTEM, "otro"), *HELLO)
    assert settle(CONFIG, ChatRequest(own)).messages == own
    assert settle(default_config(), ChatRequest(HELLO)).messages == HELLO  # the default has none


def test_another_model_never_gets_more_context_than_it_admits() -> None:
    big = LlmConfig("llama3.1:8b", 0.2, 100_000, 100, "")
    assert settle(big, ChatRequest(HELLO, "qwen2.5:0.5b")).num_ctx == MODELS["qwen2.5:0.5b"].context


@pytest.mark.parametrize(
    "request_",
    [
        ChatRequest(()),
        ChatRequest(HELLO, "gpt-4"),
        ChatRequest(HELLO, temperature=2.5),
        ChatRequest(HELLO, temperature=-0.1),
        ChatRequest(HELLO, num_ctx=10),
        ChatRequest(HELLO, num_ctx=MODELS["qwen2.5:0.5b"].context + 1),
        ChatRequest(HELLO, max_tokens=0),
    ],
    ids=["no messages", "not admitted", "hot", "cold", "tiny context", "context past the model", "no answer"],
)
def test_a_value_that_does_not_fit_is_invalid(request_: ChatRequest) -> None:
    with pytest.raises(InvalidChat):
        settle(CONFIG, request_)


def test_images_only_with_a_vision_model() -> None:
    with_image = (ChatMessage(Role.USER, "¿qué ves?", (IMAGE,)),)
    with pytest.raises(InvalidChat, match="no vision"):
        settle(CONFIG, ChatRequest(with_image))
    assert settle(CONFIG, ChatRequest(with_image, "qwen2.5vl:3b")).messages[-1].images == (IMAGE,)


@pytest.mark.parametrize("images", [("not base64!",), (IMAGE,) * (MAX_IMAGES + 1)], ids=["not base64", "too many"])
def test_bad_images_are_invalid_even_for_a_vision_model(images: tuple[str, ...]) -> None:
    with pytest.raises(InvalidChat):
        settle(CONFIG, ChatRequest((ChatMessage(Role.USER, "x", images),), "qwen2.5vl:3b"))
