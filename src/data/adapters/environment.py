"""Environment variables (the Neo4j password). `os` is only used in adapters/ (Ruff TID251)."""

import os


def environment_variable(name: str) -> str | None:
    """The variable's value, or None if it doesn't exist or is empty."""
    return os.environ.get(name) or None
