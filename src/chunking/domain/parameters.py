"""Parameters: the configurable part of the chunking resolved and checked (feature 043). A parameter the chunker
doesn't use is an error (never silently ignored); the ones it uses and weren't asked take CHUNKING_DEFAULT."""

from chunking.config import CHUNKING_DEFAULT, CHUNKING_VERSION, MAX_TOKENS_RANGE, TOKENIZERS
from chunking.models import (
    ActiveConfig,
    ChunkingParameters,
    ConfigOrigin,
    DoclingChunker,
    NoConfiguration,
    RequestedChunking,
    TokenBudget,
)

SIZED = DoclingChunker.HYBRID  # the only chunker that uses max_tokens and merge_peers


class InvalidParameters(ValueError):
    """A parameter its chunker doesn't use, a value out of range or not allowed."""


class Parameters:
    @staticmethod
    def _fit(asked: RequestedChunking, chunker: DoclingChunker) -> tuple[TokenBudget, ...]:
        """`fit` checked (feature 062): only hybrid, without tokenizer nor max_tokens, each tokenizer allowed, once,
        with a budget in range."""
        fit = asked.fit
        if fit is None:
            return ()
        if chunker is not SIZED:
            raise InvalidParameters(f"fit only goes with the {SIZED.value} chunker, not {chunker.value!r}")
        if asked.tokenizer is not None or asked.max_tokens is not None:
            raise InvalidParameters("fit replaces tokenizer and max_tokens: give fit or them, not both")
        if not fit:
            raise InvalidParameters("fit needs at least one tokenizer")
        names = [b.tokenizer for b in fit]
        repeated = sorted({n for n in names if names.count(n) > 1})
        if repeated:
            raise InvalidParameters(f"fit repeats {', '.join(repeated)}")
        low, high = MAX_TOKENS_RANGE
        for budget in fit:
            if budget.tokenizer not in TOKENIZERS:
                raise InvalidParameters(
                    f"tokenizer {budget.tokenizer!r} of fit isn't allowed; allowed: {', '.join(TOKENIZERS)}"
                )
            if not low <= budget.max_tokens <= high:
                raise InvalidParameters(f"max_tokens of {budget.tokenizer} in fit must be between {low} and {high}")
        return tuple(fit)

    @staticmethod
    def resolve(asked: RequestedChunking, docling_version: str) -> ChunkingParameters:
        """InvalidParameters if something asked can't be used."""
        chunker = asked.chunker or DoclingChunker(CHUNKING_DEFAULT.chunker)
        fit = Parameters._fit(asked, chunker)
        if fit:
            merge = CHUNKING_DEFAULT.merge_peers if asked.merge_peers is None else asked.merge_peers
            first = fit[0]
            return ChunkingParameters(
                chunker, first.tokenizer, first.max_tokens, merge, CHUNKING_VERSION, docling_version, fit
            )
        if chunker is not SIZED:
            foreign = [n for n in ("max_tokens", "merge_peers") if getattr(asked, n) is not None]
            if foreign:
                raise InvalidParameters(f"chunker {chunker.value!r} doesn't use {', '.join(foreign)}")
        tokenizer = asked.tokenizer or CHUNKING_DEFAULT.tokenizer
        if tokenizer not in TOKENIZERS:
            raise InvalidParameters(f"tokenizer {tokenizer!r} isn't allowed; allowed: {', '.join(TOKENIZERS)}")
        max_tokens = merge_peers = None
        if chunker is SIZED:
            max_tokens = CHUNKING_DEFAULT.max_tokens if asked.max_tokens is None else asked.max_tokens
            low, high = MAX_TOKENS_RANGE
            if not low <= max_tokens <= high:
                raise InvalidParameters(f"max_tokens must be between {low} and {high}")
            merge_peers = CHUNKING_DEFAULT.merge_peers if asked.merge_peers is None else asked.merge_peers
        return ChunkingParameters(chunker, tokenizer, max_tokens, merge_peers, CHUNKING_VERSION, docling_version)

    @staticmethod
    def requested(parameters: ChunkingParameters) -> RequestedChunking:
        """The configurable part of resolved parameters, as a request (what `apply` copies)."""
        if parameters.fit:
            return RequestedChunking(parameters.chunker, merge_peers=parameters.merge_peers, fit=parameters.fit)
        return RequestedChunking(
            parameters.chunker, parameters.tokenizer, parameters.max_tokens, parameters.merge_peers
        )

    @staticmethod
    def default() -> ActiveConfig:
        return ActiveConfig(RequestedChunking(), ConfigOrigin.DEFAULT)

    @staticmethod
    def active(stored: ActiveConfig | None, docling_version: str) -> tuple[ChunkingParameters, ActiveConfig]:
        """What POST /runs chunks with: the stored configuration if it is valid, else the default; NoConfiguration
        if neither is (the message says why each one failed)."""
        problems: list[str] = []
        for config in ([stored] if stored else []) + [Parameters.default()]:
            try:
                return Parameters.resolve(config.requested, docling_version), config
            except InvalidParameters as error:
                problems.append(f"{config.origin.value}: {error}")
        raise NoConfiguration("there is no configuration to chunk with (" + "; ".join(problems) + ")")
