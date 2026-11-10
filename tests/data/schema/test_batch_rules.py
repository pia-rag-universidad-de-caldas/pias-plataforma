"""The schema's rules for a batch (data.schema): composition relationships and batch_problems."""

from data.models import (
    BatchNode,
    Label,
    NodeRef,
    Relationship,
    RelationshipType,
)
from data.schema import COMPOSITION, RELATIONSHIPS, batch_problems


def test_every_composition_relationship_is_in_the_schema_and_shared_ones_are_not_composition() -> None:
    assert {d.type for d in RELATIONSHIPS} >= COMPOSITION
    shared = {RelationshipType.EXP_USA, RelationshipType.EXP_TIENE_SECCION, RelationshipType.PIPE_USA}
    assert not shared & COMPOSITION


def test_a_json_comes_from_its_raw_and_reparsing_never_deletes_it() -> None:
    json, raw = NodeRef(Label.JSON, "d"), NodeRef(Label.RAW, "d")
    nodes = [BatchNode(Label.JSON, "d", {}), BatchNode(Label.RAW, "d", {})]
    assert batch_problems(nodes, [Relationship(RelationshipType.VIENE_DE, json, raw, {})]) == []
    assert RelationshipType.VIENE_DE not in COMPOSITION


def test_batch_problems_is_empty_for_a_good_batch() -> None:
    piaa, json = NodeRef(Label.PIAA, "p"), NodeRef(Label.JSON, "d")
    nodes = [BatchNode(Label.PIAA, "p", {}), BatchNode(Label.JSON, "d", {})]
    assert batch_problems(nodes, [Relationship(RelationshipType.ES, piaa, json, {})]) == []
