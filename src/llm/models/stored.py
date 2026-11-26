"""What is stored in the graph: one TypedDict per shape, used by who writes it and by who reads it (the mappers), so
that a misspelled key is a mypy error. The keys are Neo4j property names: Spanish."""

from typing import TypedDict


class ConfigProperties(TypedDict):
    """This module's CONFIG_OFICIAL node (id `llm`)."""

    modulo: str  # "llm"
    modelo: str
    temperatura: float
    num_ctx: int
    max_tokens: int
    sistema: str
    origen: str  # ConfigOrigin
    modificado_en: str
