"""The labels and relationships embeddings reads and writes are data's (GET /data/schema): each one is there."""

from data.models import Label, RelationshipType
from data.schema import RELATIONSHIPS
from embeddings.models import GraphLabel, GraphRelation


def test_every_label_is_in_data() -> None:
    assert {label.value for label in GraphLabel} <= {label.value for label in Label}


def test_every_relationship_is_in_data_between_those_labels() -> None:
    assert {r.value for r in GraphRelation} <= {r.value for r in RelationshipType}
    assert any((d.type.value, d.source.value, d.target.value) == ("EXP_USA", "EXP_EMBEDDINGS", "EXPERIMENTO")
               for d in RELATIONSHIPS)  # fmt: skip
