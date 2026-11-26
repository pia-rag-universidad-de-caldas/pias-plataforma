"""What every repository needs to build Cypher: labels, types and vector properties as text, and integers read back."""

from typing import LiteralString

from data.models import GraphError, GraphValue, Label, RelationshipType
from data.schema.vector_rules import valid_vector_property


def name(value: Label | RelationshipType) -> LiteralString:
    """Label or type ready for Cypher (between backticks). Only values of the closed enums: Neo4j doesn't accept them
    as parameters, so they are concatenated, never user text."""
    text: LiteralString = value.value
    return "`" + text + "`"


def vector_property(text: str) -> LiteralString:
    """A vector property (`embedding_<model>_<dim>`, feature 055) ready for Cypher, between backticks. The ONLY place
    a property name that isn't a constant is concatenated: it must match the pattern of vector_rules (only lowercase
    letters, digits and _), or GraphError."""
    if not valid_vector_property(text):
        raise GraphError(f"{text!r} is not a vector property (embedding_<model>_<dimensions>)")
    checked: LiteralString = text  # validated above: [a-z0-9_] only (mypy reads LiteralString as str)
    return "`" + checked + "`"


def integer(value: GraphValue) -> int:
    if isinstance(value, int):
        return value
    raise GraphError(f"expected an integer and got {value!r}")
