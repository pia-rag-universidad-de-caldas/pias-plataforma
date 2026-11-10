"""OllamaClient: Ollama's HTTP API, the only place that talks to it (LanguageModels).

    GET  /api/version     GET /api/tags      DELETE /api/delete {model}
    POST /api/pull {model, stream: true}      (one JSON line per step, read as they come)
    POST /api/chat {model, messages, stream: false, options: {temperature, num_ctx, num_predict}}

Ollama down (network, timeout, 5xx, an answer that isn't JSON) or without the model is ModelsDown, with the reason and
what fixes it; a 400 (it refused what was sent) is InvalidChat. Never anything else: no 500 because of Ollama.
"""

import json
from collections.abc import Callable
from types import TracebackType
from typing import Self

import httpx

from llm.config import CHAT_TIMEOUT, OLLAMA_TIMEOUT, PULL_TIMEOUT
from llm.models import ChatAnswer, InstalledModel, InvalidChat, ModelsDown, PullProgress, SettledChat

from . import ollama_mappers as to

BAD_REQUEST, NOT_FOUND = 400, 404
SUCCESS = "success"  # the last status line of a pull that worked


def _error(response: httpx.Response) -> str:
    """Ollama's {"error"}, or the start of what it answered."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:300] or response.reason_phrase
    if isinstance(body, dict) and "error" in body:
        return str(body["error"])
    return str(body)[:300]


def missing(model: str) -> str:
    return f"Ollama hasn't downloaded the model {model}: ollama pull {model} (or POST /llm/models/pull)"


class OllamaClient:
    """`with OllamaClient(url) as ollama:` one httpx.Client per request or job."""

    def __init__(
        self,
        base_url: str,
        timeout: float = OLLAMA_TIMEOUT,
        chat_timeout: float = CHAT_TIMEOUT,
        pull_timeout: float = PULL_TIMEOUT,
        transport: httpx.BaseTransport | None = None,  # tests: an httpx.MockTransport
    ) -> None:
        self._url = base_url.rstrip("/")
        self._timeout, self._chat_timeout, self._pull_timeout = timeout, chat_timeout, pull_timeout
        self._client = httpx.Client(base_url=self._url, timeout=timeout, transport=transport)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, kind: type[BaseException] | None, error: BaseException | None, traceback: TracebackType | None
    ) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _down(self, route: str, error: httpx.HTTPError, timeout: float) -> ModelsDown:
        if isinstance(error, httpx.TimeoutException):
            return ModelsDown(f"Ollama ({self._url}) didn't answer {route} within {timeout}s")
        return ModelsDown(f"Ollama doesn't answer at {self._url} ({error}): is it running? (ollama serve)")

    def _send(self, method: str, route: str, body: object = None, timeout: float | None = None) -> httpx.Response:
        """The answer, with network errors and 5xx as ModelsDown (the 4xx are left to the caller)."""
        wait = timeout or self._timeout
        try:
            response = self._client.request(method, route, json=body, timeout=wait)
        except httpx.HTTPError as error:
            raise self._down(route, error, wait) from error
        if response.is_server_error:
            raise ModelsDown(f"Ollama failed {method} {route}: {response.status_code} {_error(response)}")
        return response

    def _json(self, response: httpx.Response, route: str) -> object:
        if not response.is_success:
            raise ModelsDown(f"Ollama refused {route}: {response.status_code} {_error(response)}")
        try:
            body: object = response.json()
        except ValueError as error:
            raise ModelsDown(f"Ollama answered {route} with something that isn't JSON") from error
        return body

    def version(self) -> str:
        return to.version(self._json(self._send("GET", "/api/version"), "/api/version"))

    def installed(self) -> list[InstalledModel]:
        return to.installed(self._json(self._send("GET", "/api/tags"), "/api/tags"))

    def delete(self, name: str) -> bool:
        response = self._send("DELETE", "/api/delete", {"model": name})
        if response.status_code == NOT_FOUND:
            return False
        if not response.is_success:
            raise ModelsDown(f"Ollama didn't delete {name}: {response.status_code} {_error(response)}")
        return True

    def pull(self, name: str, progress: Callable[[PullProgress], None]) -> None:
        route, last = "/api/pull", ""
        try:
            with self._client.stream(
                "POST", route, json={"model": name, "stream": True}, timeout=self._pull_timeout
            ) as response:
                if not response.is_success:
                    response.read()
                    raise ModelsDown(f"Ollama didn't pull {name}: {response.status_code} {_error(response)}")
                for line in response.iter_lines():
                    if not line.strip():
                        continue
                    try:
                        step = json.loads(line)
                    except ValueError as error:
                        raise ModelsDown(f"Ollama answered a pull line that isn't JSON: {line[:200]}") from error
                    if isinstance(step, dict) and "error" in step:
                        raise ModelsDown(f"Ollama didn't pull {name}: {step['error']}")
                    found = to.pull_step(step)
                    last = found.status
                    progress(found)
        except httpx.HTTPError as error:
            raise self._down(route, error, self._pull_timeout) from error
        if last != SUCCESS:
            raise ModelsDown(f"the pull of {name} ended without success (last step: {last or 'none'})")

    def chat(self, chat: SettledChat) -> ChatAnswer:
        route = "/api/chat"
        response = self._send("POST", route, to.chat_body(chat), self._chat_timeout)
        if response.status_code == NOT_FOUND:
            raise ModelsDown(missing(chat.model))
        if response.status_code == BAD_REQUEST:
            raise InvalidChat(f"Ollama refused the chat: {_error(response)}")
        return to.answer(self._json(response, route), chat.model)
