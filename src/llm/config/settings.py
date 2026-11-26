"""Default values of the llm module: the only list of language models of the project and the limits of a request."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    context: int  # the most tokens of context (num_ctx) the model admits
    vision: bool  # whether a message may carry images


# The models the project admits, by their Ollama name: a new one is a line. Ollama may have others: they aren't used.
MODELS: dict[str, ModelSpec] = {
    "qwen2.5:0.5b": ModelSpec(context=32768, vision=False),  # small: the real tests use it
    "llama3.1:8b": ModelSpec(context=131072, vision=False),
    "qwen2.5vl:3b": ModelSpec(context=128000, vision=True),  # reads images
}
DEFAULT_MODEL = "llama3.1:8b"  # of the active configuration when none is set

OLLAMA_URL = "http://127.0.0.1:11434"  # where Ollama listens if neither --ollama-url nor OLLAMA_URL say otherwise
OLLAMA_URL_VARIABLE = "OLLAMA_URL"  # read by server/cli.py

TEMPERATURE = 0.2  # of the default configuration: answers that stick to what they are given
TEMPERATURE_RANGE = (0.0, 2.0)
NUM_CTX = 8192  # tokens of context of the default configuration (never past the model's context)
MIN_NUM_CTX = 256
MAX_TOKENS = 1024  # tokens of an answer (Ollama's num_predict) of the default configuration
MAX_TOKENS_RANGE = (1, 32768)
SYSTEM = ""  # system prompt of the default configuration: whoever calls (consultas) brings its own
MAX_IMAGES = 8  # images per message

CHAT_TIMEOUT = 300.0  # seconds a chat may take: a large model on CPU is slow
PULL_TIMEOUT = 300.0  # seconds without a line of progress before a pull is given up
OLLAMA_TIMEOUT = 10.0  # seconds of a quick request to Ollama (version, tags, delete)
DATA_TIMEOUT = 30.0  # seconds per request to data
MAX_WAITING = 20  # pulls waiting in the line
ACTIVE_CONFIG_ID = "llm"  # the CONFIG_OFICIAL node of this module
