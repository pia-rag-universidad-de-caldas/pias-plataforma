"""OllamaClient over httpx.MockTransport: what Ollama answers becomes this module's values, and every failure of
Ollama is ModelsDown (503) or, if it refused what was sent, InvalidChat (422)."""

import json

import httpx
import pytest
from fakes import FakeOllama

from llm.adapters import OllamaClient
from llm.adapters.ollama_mappers import chat_body
from llm.models import ChatMessage, InvalidChat, ModelsDown, PullProgress, Role, SettledChat

SMALL = "qwen2.5:0.5b"
CHAT = SettledChat(SMALL, (ChatMessage(Role.USER, "hola"),), 0.2, 2048, 64)


@pytest.fixture
def ollama() -> FakeOllama:
    return FakeOllama()


def client(fake: FakeOllama) -> OllamaClient:
    return OllamaClient("http://ollama", transport=fake.transport())


def test_version_and_installed_models(ollama: FakeOllama) -> None:
    ollama.models = {SMALL: 397_000_000, "otro:1b": 10}
    with client(ollama) as found:
        assert found.version() == FakeOllama.VERSION
        installed = found.installed()
    assert [(m.name, m.size, m.family) for m in installed] == [("otro:1b", 10, "otro"), (SMALL, 397_000_000, "qwen2.5")]
    assert installed[0].modified == "2026-11-01T10:00:00Z"


def test_chat_sends_the_options_and_reads_the_answer(ollama: FakeOllama) -> None:
    ollama.models = {SMALL: 1}
    with client(ollama) as found:
        answer = found.chat(CHAT)
    assert (answer.model, answer.content, answer.prompt_tokens, answer.answer_tokens) == (SMALL, "eco: hola", 12, 3)
    assert answer.seconds == 1.5
    sent = ollama.chats[0]
    assert sent["stream"] is False and sent["options"] == {"temperature": 0.2, "num_ctx": 2048, "num_predict": 64}
    assert sent["messages"] == [{"role": "user", "content": "hola"}]


def test_images_go_in_their_message() -> None:
    message = ChatMessage(Role.USER, "¿qué ves?", ("aGVsbG8=",))
    body = chat_body(SettledChat("qwen2.5vl:3b", (message,), 0.2, 2048, 64))
    assert body["messages"] == [{"role": "user", "content": "¿qué ves?", "images": ["aGVsbG8="]}]


def test_a_model_not_downloaded_is_down_with_the_pull_that_fixes_it(ollama: FakeOllama) -> None:
    with client(ollama) as found, pytest.raises(ModelsDown, match=f"ollama pull {SMALL}"):
        found.chat(CHAT)


def test_without_ollama_everything_is_down(ollama: FakeOllama) -> None:
    ollama.down = True
    with client(ollama) as found:
        for call in (found.version, found.installed, lambda: found.chat(CHAT), lambda: found.delete(SMALL)):
            with pytest.raises(ModelsDown, match="doesn't answer"):
                call()


def test_a_timeout_is_down() -> None:
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    found = OllamaClient("http://ollama", transport=httpx.MockTransport(slow))
    with found, pytest.raises(ModelsDown, match="within"):
        found.chat(CHAT)


@pytest.mark.parametrize(("status", "error"), [(500, ModelsDown), (400, InvalidChat)])
def test_ollama_failing_or_refusing(ollama: FakeOllama, status: int, error: type[Exception]) -> None:
    ollama.failure = status
    with client(ollama) as found, pytest.raises(error, match="it broke"):
        found.chat(CHAT)


def test_an_answer_that_is_not_json_is_down() -> None:
    found = OllamaClient("http://ollama", transport=httpx.MockTransport(lambda _: httpx.Response(200, text="<html>")))
    with found, pytest.raises(ModelsDown, match="isn't JSON"):
        found.version()


def test_pull_tells_each_step_and_ends_in_success(ollama: FakeOllama) -> None:
    steps: list[PullProgress] = []
    with client(ollama) as found:
        found.pull(SMALL, steps.append)
    assert steps[1] == PullProgress("pulling abc", 50, 100) and steps[-1].status == "success"
    assert SMALL in ollama.models


def test_a_pull_that_ollama_refuses_is_down(ollama: FakeOllama) -> None:
    ollama.pull_error = "pull model manifest: file does not exist"
    with client(ollama) as found, pytest.raises(ModelsDown, match="file does not exist"):
        found.pull("nope:1b", lambda _: None)


def test_a_pull_that_ends_without_success_is_down() -> None:
    lines = "\n".join(json.dumps(line) for line in [{"status": "pulling manifest"}])
    transport = httpx.MockTransport(lambda _: httpx.Response(200, content=lines.encode()))
    with OllamaClient("http://ollama", transport=transport) as found, pytest.raises(ModelsDown, match="without"):
        found.pull(SMALL, lambda _: None)


def test_delete_says_whether_it_had_it(ollama: FakeOllama) -> None:
    ollama.models = {SMALL: 1}
    with client(ollama) as found:
        assert found.delete(SMALL) is True
        assert found.delete(SMALL) is False
