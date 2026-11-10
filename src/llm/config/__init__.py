"""Values of the llm module, where Ollama is and the location of data (its active configuration)."""

from common.config import DATA_PATH, HTTP_TIMEOUT

from .settings import (
    ACTIVE_CONFIG_ID,
    CHAT_TIMEOUT,
    DATA_TIMEOUT,
    DEFAULT_MODEL,
    MAX_IMAGES,
    MAX_TOKENS,
    MAX_TOKENS_RANGE,
    MAX_WAITING,
    MIN_NUM_CTX,
    MODELS,
    NUM_CTX,
    OLLAMA_TIMEOUT,
    OLLAMA_URL,
    OLLAMA_URL_VARIABLE,
    PULL_TIMEOUT,
    SYSTEM,
    TEMPERATURE,
    TEMPERATURE_RANGE,
    ModelSpec,
)

__all__ = [
    "ACTIVE_CONFIG_ID",
    "CHAT_TIMEOUT",
    "DATA_PATH",
    "DATA_TIMEOUT",
    "DEFAULT_MODEL",
    "HTTP_TIMEOUT",
    "MAX_IMAGES",
    "MAX_TOKENS",
    "MAX_TOKENS_RANGE",
    "MAX_WAITING",
    "MIN_NUM_CTX",
    "MODELS",
    "NUM_CTX",
    "OLLAMA_TIMEOUT",
    "OLLAMA_URL",
    "OLLAMA_URL_VARIABLE",
    "PULL_TIMEOUT",
    "SYSTEM",
    "TEMPERATURE",
    "TEMPERATURE_RANGE",
    "ModelSpec",
]
