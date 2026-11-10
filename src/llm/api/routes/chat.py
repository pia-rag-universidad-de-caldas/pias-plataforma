"""POST /chat: messages (and, with a vision model, images) in, the model's answer out. Synchronous, with a timeout
(config.CHAT_TIMEOUT); no conversation is kept (that is consultas', feature 048). Streaming is left for a separate
route (feature 052)."""

from fastapi import APIRouter

from llm.api.dependencies import Config, Ollama
from llm.api.responses import INVALID, OLLAMA_DOWN
from llm.api.schemas import AnswerMessage, ChatView, NewChat
from llm.domain import resolve, settle
from llm.models import ChatMessage, ChatRequest, Role

router = APIRouter(tags=["chat"])


def chat_request(body: NewChat) -> ChatRequest:
    messages = tuple(ChatMessage(Role(m.role), m.content, tuple(m.images or ())) for m in body.messages)
    return ChatRequest(messages, body.model, body.temperature, body.num_ctx, body.max_tokens)


@router.post("/chat", responses=OLLAMA_DOWN | INVALID)
def chat(config: Config, ollama: Ollama, body: NewChat) -> ChatView:
    """What isn't sent (model, temperature, num_ctx, max_tokens) comes from the active configuration, and its system
    prompt goes first if the messages bring none. 422 if the model isn't admitted, a value is out of range or there
    are images for a model without vision; 503 if Ollama doesn't answer or hasn't downloaded the model."""
    settled = settle(resolve(config), chat_request(body))
    answer = ollama.chat(settled)
    return ChatView(
        answer.model,
        AnswerMessage("assistant", answer.content),
        answer.prompt_tokens,
        answer.answer_tokens,
        answer.seconds,
    )
