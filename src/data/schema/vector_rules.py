"""What a vector index may be (features 046 and 055). The names and dimensions come from whoever asks (embeddings,
which knows the models); the rules are data's: a valid name, only over the labels that hold vectors, and a vector
property per model (`embedding_<model>_<dim>`), so that two models live side by side on the same label.

Neo4j admits ONE vector index per label and property: with the model in the property's name, each model has its own.
"""

import re

from data.models import Label

LEGACY_PROPERTY = "embedding"  # where every vector lived before feature 055 (the migration moves it)
MAX_DIMENSIONS = 4096  # what Neo4j admits
VECTOR_LABELS = (Label.FRAGMENTOS, Label.EXP_EMBED)  # official chunks, and the vectors of embeddings experiments
_NAME = re.compile(r"vec_[a-z0-9_]{1,120}")
_PROPERTY = re.compile(r"embedding_[a-z0-9_]{1,120}")


def valid_index_name(name: str) -> bool:
    return _NAME.fullmatch(name) is not None


def valid_vector_property(name: str) -> bool:
    """embedding_ followed by lowercase letters, digits or _: the only property names concatenated into Cypher."""
    return _PROPERTY.fullmatch(name) is not None


def is_vector_property(key: str) -> bool:
    """A property that holds a vector (the legacy one included): what ?omit=embedding leaves out."""
    return key == LEGACY_PROPERTY or valid_vector_property(key)


def index_problems(name: str, label: Label, dimensions: int, property: str) -> list[str]:
    """Everything wrong with the index asked for; empty if it can be created."""
    problems: list[str] = []
    if not valid_index_name(name):
        problems.append("the name must be vec_ followed by 1 to 120 lowercase letters, digits or _")
    if not valid_vector_property(property):
        problems.append("the property must be embedding_ followed by 1 to 120 lowercase letters, digits or _")
    if not 1 <= dimensions <= MAX_DIMENSIONS:
        problems.append(f"dimensions must be between 1 and {MAX_DIMENSIONS}")
    if label not in VECTOR_LABELS:
        problems.append(f"only these labels have vectors: {' or '.join(VECTOR_LABELS)}")
    return problems
