"""LlmClient: the contract of features 047 and 048 with the llm module.

    POST {llm}/chat {messages: [{role, content, images?}], model?, temperature?, num_ctx?, max_tokens?}
                  → {model, message: {role: "assistant", content}, prompt_tokens, answer_tokens, seconds}
    GET  {llm}/models   → {admitted: [{name, vision, installed, ...}], ...}   (which one describes an image)
    GET  {llm}/config   → {model, ...}                                       (whether the answer sees the images)

Network, timeout, 5xx (Ollama down, the model not downloaded) or no route: LlmDown (503); a 4xx (a model it doesn't
admit, a parameter out of range): InvalidQuestion (422), with llm's reason. What isn't sent is llm's active
configuration.
"""

from collections.abc import Sequence

import httpx

from common.http import BaseHttpClient, ErrorPolicy
from consultas.models import InvalidQuestion, LlmDown, LlmModel, LlmOptions, Message, Reply

from . import mappers as to

LLM_ERRORS = ErrorPolicy("llm", LlmDown, InvalidQuestion)


def chat_body(messages: Sequence[Message], options: LlmOptions) -> dict[str, object]:
    sent: list[dict[str, object]] = []
    for m in messages:
        message: dict[str, object] = {"role": m.role.value, "content": m.content}
        if m.images:
            message["images"] = list(m.images)
        sent.append(message)
    body: dict[str, object] = {"messages": sent}
    overrides = {
        "model": options.model,
        "temperature": options.temperature,
        "num_ctx": options.num_ctx,
        "max_tokens": options.max_tokens,
    }
    body.update({key: value for key, value in overrides.items() if value is not None})
    return body


class LlmClient(BaseHttpClient):
    """`path`: llm's prefix in the server (/llm)."""

    def __init__(self, client: httpx.Client, path: str) -> None:
        super().__init__(client, path, LLM_ERRORS)

    def chat(self, messages: Sequence[Message], options: LlmOptions) -> Reply:
        response = self._request("POST", "/chat", body=chat_body(messages, options))
        if response is None:
            raise LlmDown(f"it has no {self._path}/chat route (feature 047)")
        return to.reply(self._json(response), LlmDown)

    def models(self) -> list[LlmModel]:
        found = self._get("/models")
        if found is None:
            raise LlmDown(f"it has no {self._path}/models route")
        return to.models(found, LlmDown)

    def active_model(self) -> str:
        found = self._get("/config")
        if found is None:
            raise LlmDown(f"it has no {self._path}/config route")
        return to.active_model(found, LlmDown)
