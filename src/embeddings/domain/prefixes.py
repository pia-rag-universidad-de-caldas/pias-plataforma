"""What a model reads in front of a text (feature 055): e5 was trained with `query: ` before a question and
`passage: ` before a document, and gives worse vectors without them. The prefix is part of the text it reads, so it
counts in its tokens (check_lengths counts the prefixed text). A model without prefixes reads the text as it is."""

from embeddings.config import MODELS


def passages(model: str, texts: list[str]) -> list[str]:
    """Chunks (runs and experiments), with the model's passage prefix."""
    prefix = MODELS[model].passage_prefix
    return [prefix + text for text in texts] if prefix else list(texts)


def queries(model: str, texts: list[str]) -> list[str]:
    """Questions (POST /vectors), with the model's query prefix."""
    prefix = MODELS[model].query_prefix
    return [prefix + text for text in texts] if prefix else list(texts)
