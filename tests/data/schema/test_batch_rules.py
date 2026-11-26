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
    shared = {RelationshipType.EXP_USA, RelationshipType.EXP_DE, RelationshipType.PIPE_USA}
    assert not shared & COMPOSITION


def test_an_experiment_owns_its_documents_sections_chunks_and_vectors() -> None:
    """Feature 055 part b: replace_from an EXPERIMENTO goes down to its EXP_EMBED, and never up to the JSON."""
    T = RelationshipType
    owned = {T.EXP_TIENE_DOCUMENTO, T.EXP_TIENE_SECCION, T.EXP_TIENE_CHUNK, T.EXP_TIENE_VECTOR}
    assert owned <= COMPOSITION
    experiment, document = NodeRef(Label.EXPERIMENTO, "e"), NodeRef(Label.EXP_DOCUMENTO, "e:d")
    nodes = [BatchNode(Label.EXPERIMENTO, "e", {}), BatchNode(Label.EXP_DOCUMENTO, "e:d", {})]
    links = [
        Relationship(T.EXP_TIENE_DOCUMENTO, experiment, document, {}),
        Relationship(T.EXP_DE, document, NodeRef(Label.JSON, "d"), {}),
    ]
    assert batch_problems(nodes, links) == []


def test_the_shapes_of_before_feature_055b_leave_the_schema() -> None:
    nodes = [BatchNode(Label.EXPERIMENTO, "e", {}), BatchNode(Label.JSON, "d", {})]
    old = Relationship(RelationshipType.EXP_USA, NodeRef(Label.EXPERIMENTO, "e"), NodeRef(Label.JSON, "d"), {})
    assert batch_problems(nodes, [old]) != []
    assert not {"EXP_GENERA", "EXP_TIENE_PUNTUACION"} & {t.value for t in RelationshipType}
    assert "EXP_PUNTUACION" not in {label.value for label in Label}


def test_a_comparison_owns_its_questions_but_not_the_chunks_they_cite() -> None:
    """Feature 060: replace_from a COMPARACION takes its CONSULTA (COMPARA), never the FRAGMENTOS they cite."""
    comparison, question = NodeRef(Label.COMPARACION, "c"), NodeRef(Label.CONSULTA, "q")
    nodes = [BatchNode(Label.COMPARACION, "c", {}), BatchNode(Label.CONSULTA, "q", {})]
    link = Relationship(RelationshipType.COMPARA, comparison, question, {"panel": 0, "etiqueta": "Panel 1"})
    assert batch_problems(nodes, [link]) == []
    assert RelationshipType.COMPARA in COMPOSITION and RelationshipType.RESPONDIDA_CON not in COMPOSITION


def test_a_json_comes_from_its_raw_and_reparsing_never_deletes_it() -> None:
    json, raw = NodeRef(Label.JSON, "d"), NodeRef(Label.RAW, "d")
    nodes = [BatchNode(Label.JSON, "d", {}), BatchNode(Label.RAW, "d", {})]
    assert batch_problems(nodes, [Relationship(RelationshipType.VIENE_DE, json, raw, {})]) == []
    assert RelationshipType.VIENE_DE not in COMPOSITION


def test_batch_problems_is_empty_for_a_good_batch() -> None:
    piaa, json = NodeRef(Label.PIAA, "p"), NodeRef(Label.JSON, "d")
    nodes = [BatchNode(Label.PIAA, "p", {}), BatchNode(Label.JSON, "d", {})]
    assert batch_problems(nodes, [Relationship(RelationshipType.ES, piaa, json, {})]) == []
