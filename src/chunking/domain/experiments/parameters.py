"""Parameters: which parameters each chunking strategy of an experiment uses, their defaults and their limits
(feature 025). A parameter asked for a strategy that doesn't use it is an error (never silently ignored); the ones a
strategy uses and weren't asked take their config default; the others are None."""

from dataclasses import fields

from chunking.config import (
    EMBEDDING_MODEL,
    EMBEDDING_MODELS,
    MAX_TOKENS,
    MAX_TOKENS_RANGE,
    MERGE_PEERS,
    OVERLAP_TOKENS,
    SIMILARITY_THRESHOLD,
    STRATEGY,
    TOKENIZER,
    TOKENIZERS,
)
from chunking.models import ChunkingStrategy, RequestedStrategy, StrategyParameters

S = ChunkingStrategy
COMMON = frozenset({"strategy", "tokenizer"})
# What each strategy uses besides COMMON. `element` never splits, so max_tokens doesn't apply to it.
USES: dict[ChunkingStrategy, frozenset[str]] = {
    S.HYBRID: frozenset({"max_tokens", "merge_peers"}),
    S.ELEMENT: frozenset(),
    S.SECTION: frozenset({"max_tokens"}),
    S.PAGE: frozenset({"max_tokens"}),
    S.FIXED: frozenset({"max_tokens", "overlap_tokens"}),
    S.POINTS: frozenset({"max_tokens"}),
    S.SEMANTIC: frozenset({"max_tokens", "embedding_model", "similarity_threshold"}),
}


class InvalidParameters(ValueError):
    """Parameters that can't be used together, a value out of range or not allowed, a malformed plan rule."""


class Parameters:
    @staticmethod
    def resolve(asked: RequestedStrategy) -> StrategyParameters:
        strategy = asked.strategy or ChunkingStrategy(STRATEGY)
        uses = COMMON | USES[strategy]
        foreign = [f.name for f in fields(asked) if getattr(asked, f.name) is not None and f.name not in uses]
        if foreign:
            raise InvalidParameters(f"strategy {strategy.value!r} doesn't use {', '.join(foreign)}")
        tokenizer = asked.tokenizer or TOKENIZER
        if tokenizer not in TOKENIZERS:
            raise InvalidParameters(f"tokenizer {tokenizer!r} isn't allowed; allowed: {', '.join(TOKENIZERS)}")

        def own[T](name: str, asked_value: T | None, default: T) -> T | None:
            if name not in uses:
                return None
            return default if asked_value is None else asked_value

        max_tokens = own("max_tokens", asked.max_tokens, MAX_TOKENS)
        if max_tokens is not None and not MAX_TOKENS_RANGE[0] <= max_tokens <= MAX_TOKENS_RANGE[1]:
            raise InvalidParameters(f"max_tokens must be between {MAX_TOKENS_RANGE[0]} and {MAX_TOKENS_RANGE[1]}")
        overlap = own("overlap_tokens", asked.overlap_tokens, OVERLAP_TOKENS)
        if overlap is not None and max_tokens is not None and not 0 <= overlap < max_tokens:
            raise InvalidParameters(f"overlap_tokens must be at least 0 and less than max_tokens ({max_tokens})")
        model = own("embedding_model", asked.embedding_model, EMBEDDING_MODEL)
        if model is not None and model not in EMBEDDING_MODELS:
            raise InvalidParameters(f"embedding_model {model!r} isn't allowed; allowed: {', '.join(EMBEDDING_MODELS)}")
        threshold = own("similarity_threshold", asked.similarity_threshold, SIMILARITY_THRESHOLD)
        if threshold is not None and not 0 <= threshold <= 1:
            raise InvalidParameters("similarity_threshold must be between 0 and 1")
        return StrategyParameters(
            strategy=strategy,
            tokenizer=tokenizer,
            max_tokens=max_tokens,
            merge_peers=own("merge_peers", asked.merge_peers, MERGE_PEERS),
            overlap_tokens=overlap,
            embedding_model=model,
            similarity_threshold=threshold,
        )
