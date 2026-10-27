"""What every repository needs to build Cypher: labels and types as text, and integers read back."""

from typing import LiteralString

from data.models import GraphError, GraphValue, Label, RelationshipType


def name(value: Label | RelationshipType) -> LiteralString:
    """Label or type ready for Cypher (between backticks). Only values of the closed enums: Neo4j doesn't accept them
    as parameters, so they are concatenated, never user text."""
    text: LiteralString = value.value
    return "`" + text + "`"


def integer(value: GraphValue) -> int:
    if isinstance(value, int):
        return value
    raise GraphError(f"expected an integer and got {value!r}")
