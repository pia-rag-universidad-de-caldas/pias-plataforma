"""GET /chats, GET/DELETE /chats/{id}: the stored conversations, with their questions and sources."""

from fastapi import APIRouter, HTTPException, status

from consultas.api.dependencies import Chats
from consultas.api.responses import DOWN, NOT_FOUND
from consultas.models import ChatDetail, ChatSummary

router = APIRouter(prefix="/chats", tags=["chats"])


def _missing(id: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"there is no chat {id!r}")


@router.get("", responses=DOWN)
def list_chats(chats: Chats) -> list[ChatSummary]:
    """The most recently modified first."""
    return chats.chats()


@router.get("/{id}", responses=DOWN | NOT_FOUND)
def read_chat(chats: Chats, id: str) -> ChatDetail:
    """The chat and its questions, oldest first, each with its answer and the chunks it cited."""
    found = chats.detail(id)
    if found is None:
        raise _missing(id)
    return found


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT, responses=DOWN | NOT_FOUND)
def delete_chat(chats: Chats, id: str) -> None:
    """The chat and its questions; the chunks they cite stay."""
    if not chats.delete(id):
        raise _missing(id)
