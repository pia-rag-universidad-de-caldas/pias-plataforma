"""The token limit of a request: asked or the model's default, never past what the model admits."""

from dataclasses import dataclass

from embeddings.config import MODELS, ModelSpec
from embeddings.models import InvalidLimit

from .events import HEADING_TOKENS


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


SPECIAL_TOKENS = 2  # [CLS] and [SEP]: the limits count them, a chunk's tokens (chunking's) don't


@dataclass(frozen=True)
class PassageBudgets:
    """How many tokens of its own tokenizer a chunk may have for a model (feature 062): what chunking's `fit` asks
    for. None when the prefix can't be counted."""

    passage: int | None  # max_tokens - 2 - prefix: the most the model reads
    default: int | None  # default_tokens - 2 - prefix: with the model's default limit
    official: int | None  # the default one, leaving HEADING_TOKENS for the course in front when the positions end


def passage_budgets(spec: ModelSpec, prefix_tokens: int | None) -> PassageBudgets:
    """An official chunk gets the course in front (feature 057): the model reads up to HEADING_TOKENS more, but never
    past its positions, so where default_tokens + HEADING_TOKENS goes over max_tokens the chunk gives that room up."""
    if prefix_tokens is None:
        return PassageBudgets(None, None, None)
    room = SPECIAL_TOKENS + prefix_tokens
    official = min(spec.default_tokens, spec.max_tokens - HEADING_TOKENS)
    return PassageBudgets(spec.max_tokens - room, spec.default_tokens - room, official - room)
