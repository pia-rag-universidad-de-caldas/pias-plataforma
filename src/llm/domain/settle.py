"""A chat on the active configuration: what it doesn't send comes from the configuration, everything is checked before
Ollama is asked."""

import binascii
from base64 import b64decode

from llm.config import MAX_IMAGES
from llm.models import ChatMessage, ChatRequest, InvalidChat, LlmConfig, Role, SettledChat

from .validation import admitted, check_values


def _check_images(model: str, vision: bool, messages: tuple[ChatMessage, ...]) -> None:
    for number, message in enumerate(messages, 1):
        if not message.images:
            continue
        if not vision:
            raise InvalidChat(f"message {number} has images and {model} has no vision: use a vision model")
        if len(message.images) > MAX_IMAGES:
            raise InvalidChat(f"message {number} has {len(message.images)} images; at most {MAX_IMAGES}")
        for image in message.images:
            try:
                b64decode(image, validate=True)
            except (binascii.Error, ValueError) as error:
                raise InvalidChat(f"an image of message {number} isn't base64: {error}") from error


def settle(config: LlmConfig, request: ChatRequest) -> SettledChat:
    """InvalidChat if the model isn't admitted, a value is out of range, there are no messages, or there are images
    for a model without vision. The configuration's system prompt goes first if the messages bring none."""
    if not request.messages:
        raise InvalidChat("a chat needs at least one message")
    model = request.model or config.model
    spec = admitted(model)
    temperature = config.temperature if request.temperature is None else request.temperature
    num_ctx = request.num_ctx
    if num_ctx is None:
        num_ctx = config.num_ctx if model == config.model else min(config.num_ctx, spec.context)
    max_tokens = config.max_tokens if request.max_tokens is None else request.max_tokens
    check_values(model, temperature, num_ctx, max_tokens)
    _check_images(model, spec.vision, request.messages)
    messages = request.messages
    if config.system and not any(m.role is Role.SYSTEM for m in messages):
        messages = (ChatMessage(Role.SYSTEM, config.system), *messages)
    return SettledChat(model, messages, temperature, num_ctx, max_tokens)
