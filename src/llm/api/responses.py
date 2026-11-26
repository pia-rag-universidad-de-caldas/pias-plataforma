"""What the routes declare about their errors."""

from common.api import Error

type Responses = dict[int | str, dict[str, object]]


def error(code: int, description: str) -> Responses:
    return {code: {"model": Error, "description": description}}


OLLAMA_DOWN = error(503, "Ollama doesn't answer or hasn't downloaded the model (ollama pull <model>), or data is down")
DATA_DOWN = error(503, "data is not answering")
INVALID = error(422, "an unknown key, a model that isn't admitted, a value out of range or images without vision")
REFUSED = error(502, "data refused what was sent")
