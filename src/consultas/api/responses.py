"""What the routes declare about their errors."""

from common.api import Error

type Responses = dict[int | str, dict[str, object]]


def error(code: int, description: str) -> Responses:
    return {code: {"model": Error, "description": description}}


DOWN = error(
    503,
    "embeddings, llm, data or parsing (or what is behind them) is not answering, or no vision model is downloaded for"
    " an image: the message says which",
)
INVALID = error(422, "an unknown key, a value out of range, or what llm or embeddings doesn't admit")
REFUSED = error(502, "data refused what was sent")
NOT_FOUND = error(404, "no chat, or no embeddings experiment, with that id")
CONFLICT = error(409, "the embeddings experiment didn't finish, or the chat is of the other kind")
