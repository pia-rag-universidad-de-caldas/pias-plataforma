"""What the routes declare about their errors."""

from common.api import Error

type Responses = dict[int | str, dict[str, object]]


def error(code: int, description: str) -> Responses:
    return {code: {"model": Error, "description": description}}


DOWN = error(503, "data is not answering, or the model can't be loaded (uv sync --extra embed)")
INVALID = error(422, "an unknown key, a model that isn't served or a max_tokens it doesn't admit")
REFUSED = error(502, "data refused what was sent")
