"""The labels and relationships consultas writes are data's: each one is there, between those labels."""

from consultas.models import GraphLabel, GraphRelation
from data.models import Label, RelationshipType
from data.schema import definition


def test_every_label_and_relationship_is_in_data() -> None:
    assert {label.value for label in GraphLabel} <= {label.value for label in Label}
    assert {r.value for r in GraphRelation} <= {r.value for r in RelationshipType}


def test_a_question_may_cite_official_and_experiment_chunks() -> None:
    for chunk in (Label.FRAGMENTOS, Label.EXP_CHUNK):
        assert definition(RelationshipType.RESPONDIDA_CON, Label.CONSULTA, chunk) is not None
    assert definition(RelationshipType.GENERA, Label.CHAT, Label.CONSULTA) is not None
