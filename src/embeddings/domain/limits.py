"""The token limit of a request: asked or the model's default, never past what the model admits."""

from embeddings.config import MODELS
from embeddings.models import InvalidLimit


def token_limit(model: str, asked: int | None) -> int:
    """InvalidLimit if the model isn't one of MODELS or the limit is out of 1..its max_tokens."""
    spec = MODELS.get(model)
    if spec is None:
        raise InvalidLimit(f"the model {model!r} isn't served; served: {sorted(MODELS)}")
    if asked is None:
        return spec.default_tokens
    if not 1 <= asked <= spec.max_tokens:
        raise InvalidLimit(f"max_tokens must be between 1 and {spec.max_tokens} for {model}, not {asked}")
    return asked
