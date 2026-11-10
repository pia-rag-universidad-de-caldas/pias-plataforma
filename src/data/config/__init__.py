"""Neo4j connection and graph API settings."""

from common.config import MAX_PER_PAGE, PER_PAGE

from .settings import (
    NEO4J_DATABASE,
    NEO4J_URL,
    NEO4J_USER,
    PASSWORD_VARIABLE,
)

__all__ = [
    "MAX_PER_PAGE",
    "NEO4J_DATABASE",
    "NEO4J_URL",
    "NEO4J_USER",
    "PASSWORD_VARIABLE",
    "PER_PAGE",
]
