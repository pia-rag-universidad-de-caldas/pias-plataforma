"""Ollama's names: `llama3.1` and `llama3.1:latest` are the same model."""

LATEST = "latest"


def canonical(name: str) -> str:
    """The name with its tag: `latest` if it has none."""
    return name if ":" in name.rsplit("/", 1)[-1] else f"{name}:{LATEST}"


def same_model(one: str, other: str) -> bool:
    return canonical(one) == canonical(other)
