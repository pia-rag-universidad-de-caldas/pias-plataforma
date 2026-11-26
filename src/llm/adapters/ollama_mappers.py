"""Ollama's JSON as this module's values, and a settled chat as Ollama's body. A value of an unexpected type is read as
missing; an answer without what it must have is ModelsDown (Ollama answered something it shouldn't)."""

from collections.abc import Mapping

from llm.models import ChatAnswer, InstalledModel, ModelsDown, PullProgress, SettledChat

NANOSECONDS = 1e9  # Ollama's durations


def _text(raw: Mapping[str, object], key: str) -> str | None:
    value = raw.get(key)
    return value if isinstance(value, str) else None


def _integer(raw: Mapping[str, object], key: str) -> int:
    value = raw.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def version(body: object) -> str:
    found = _text(body, "version") if isinstance(body, Mapping) else None
    if found is None:
        raise ModelsDown(f"Ollama answered /api/version without a version: {str(body)[:200]}")
    return found


def installed_model(raw: Mapping[str, object]) -> InstalledModel | None:
    name = _text(raw, "name") or _text(raw, "model")
    if not name:
        return None
    details = raw.get("details")
    family = _text(details, "family") if isinstance(details, Mapping) else None
    return InstalledModel(name, _integer(raw, "size"), family, _text(raw, "modified_at"))


def installed(body: object) -> list[InstalledModel]:
    models = body.get("models") if isinstance(body, Mapping) else None
    if not isinstance(models, list):
        raise ModelsDown(f"Ollama answered /api/tags without a list of models: {str(body)[:200]}")
    found = (installed_model(raw) for raw in models if isinstance(raw, Mapping))
    return sorted((m for m in found if m is not None), key=lambda m: m.name)


def pull_step(step: object) -> PullProgress:
    if not isinstance(step, Mapping):
        return PullProgress("")
    return PullProgress(_text(step, "status") or "", _integer(step, "completed"), _integer(step, "total"))


def chat_body(chat: SettledChat) -> dict[str, object]:
    messages: list[dict[str, object]] = []
    for message in chat.messages:
        sent: dict[str, object] = {"role": message.role.value, "content": message.content}
        if message.images:
            sent["images"] = list(message.images)
        messages.append(sent)
    return {
        "model": chat.model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": chat.temperature, "num_ctx": chat.num_ctx, "num_predict": chat.max_tokens},
    }


def answer(body: object, model: str) -> ChatAnswer:
    message = body.get("message") if isinstance(body, Mapping) else None
    content = _text(message, "content") if isinstance(message, Mapping) else None
    if not isinstance(body, Mapping) or content is None:
        raise ModelsDown(f"Ollama answered a chat without a message: {str(body)[:200]}")
    return ChatAnswer(
        _text(body, "model") or model,
        content,
        _integer(body, "prompt_eval_count"),
        _integer(body, "eval_count"),
        round(_integer(body, "total_duration") / NANOSECONDS, 3),
    )
