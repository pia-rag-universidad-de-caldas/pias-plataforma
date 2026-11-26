"""GraphBatchWriter against a real Neo4j (omitted without one): what a batch really does to the graph."""

import pytest

from data.models import (
    BatchError,
    BatchNode,
    GraphAdapter,
    Label,
    NodeMode,
    NodeRef,
    Relationship,
    RelationshipType,
)
from data.repository import PiaaRepository

pytestmark = pytest.mark.neo4j


def node(label: Label, id: str, mode: NodeMode = NodeMode.REPLACE, **properties: str | int) -> BatchNode:
    return BatchNode(label, id, dict(properties), mode)


def link(type: RelationshipType, source: tuple[Label, str], target: tuple[Label, str]) -> Relationship:
    return Relationship(type, NodeRef(*source), NodeRef(*target), {})


def exists(graph: GraphAdapter, label: Label, id: str) -> bool:
    return PiaaRepository(graph).node(label, id) is not None


@pytest.fixture
def tree(real_graph: GraphAdapter, test_prefix: str) -> dict[str, str]:
    """A JSON with a section, a chunk and a finding; the finding is of an antipattern, which isn't only its."""
    ids = {name: f"{test_prefix}-{name}" for name in ("json", "seccion", "fragmento", "hallazgo", "antipatron")}
    PiaaRepository(real_graph).write_batch(
        [
            node(Label.JSON, ids["json"], nombre="a"),
            node(Label.SECCION, ids["seccion"]),
            node(Label.FRAGMENTOS, ids["fragmento"]),
            node(Label.HALLAZGOS, ids["hallazgo"]),
            node(Label.ANTIPATRON, ids["antipatron"]),
        ],
        [
            link(RelationshipType.TIENE_SECCION, (Label.JSON, ids["json"]), (Label.SECCION, ids["seccion"])),
            link(
                RelationshipType.TIENE_FRAGMENTO, (Label.SECCION, ids["seccion"]), (Label.FRAGMENTOS, ids["fragmento"])
            ),
            link(RelationshipType.TIENE, (Label.JSON, ids["json"]), (Label.HALLAZGOS, ids["hallazgo"])),
            link(RelationshipType.DE_TIPO, (Label.HALLAZGOS, ids["hallazgo"]), (Label.ANTIPATRON, ids["antipatron"])),
        ],
        None,
    )
    return ids


def test_replace_from_deletes_what_hangs_from_the_node(real_graph: GraphAdapter, tree: dict[str, str]) -> None:
    result = PiaaRepository(real_graph).write_batch([], [], NodeRef(Label.JSON, tree["json"]))
    assert result.deleted == 3
    assert not exists(real_graph, Label.SECCION, tree["seccion"])
    assert not exists(real_graph, Label.FRAGMENTOS, tree["fragmento"])


def test_replace_from_keeps_the_node_itself(real_graph: GraphAdapter, tree: dict[str, str]) -> None:
    PiaaRepository(real_graph).write_batch([], [], NodeRef(Label.JSON, tree["json"]))
    assert exists(real_graph, Label.JSON, tree["json"])


def test_replace_from_doesnt_follow_what_isnt_composition(real_graph: GraphAdapter, tree: dict[str, str]) -> None:
    PiaaRepository(real_graph).write_batch([], [], NodeRef(Label.JSON, tree["json"]))
    assert exists(real_graph, Label.ANTIPATRON, tree["antipatron"])


def test_replace_sets_only_the_properties_sent(real_graph: GraphAdapter, test_prefix: str) -> None:
    repository = PiaaRepository(real_graph)
    repository.write_batch([node(Label.JSON, test_prefix, a=1, b=2)], [], None)
    result = repository.write_batch([node(Label.JSON, test_prefix, b=3)], [], None)
    found = repository.node(Label.JSON, test_prefix)
    assert found is not None
    assert (found.properties, result.replaced) == ({"b": 3}, 1)


def test_ensure_leaves_alone_what_exists(real_graph: GraphAdapter, test_prefix: str) -> None:
    repository = PiaaRepository(real_graph)
    repository.write_batch([node(Label.PIAA, test_prefix, NodeMode.ENSURE, a=1)], [], None)
    result = repository.write_batch([node(Label.PIAA, test_prefix, NodeMode.ENSURE, a=2)], [], None)
    found = repository.node(Label.PIAA, test_prefix)
    assert found is not None
    assert (found.properties, result.kept, result.created) == ({"a": 1}, 1, 0)


def test_merge_sets_what_is_sent_and_keeps_the_rest(real_graph: GraphAdapter, test_prefix: str) -> None:
    repository = PiaaRepository(real_graph)
    repository.write_batch([node(Label.JSON, test_prefix, a=1, b=2)], [], None)
    result = repository.write_batch([node(Label.JSON, test_prefix, NodeMode.MERGE, b=3)], [], None)
    found = repository.node(Label.JSON, test_prefix)
    assert found is not None
    assert (found.properties, result.merged) == ({"a": 1, "b": 3}, 1)


def test_a_relationship_is_not_repeated_by_writing_it_again(real_graph: GraphAdapter, test_prefix: str) -> None:
    repository = PiaaRepository(real_graph)
    json, section = f"{test_prefix}-j", f"{test_prefix}-s"
    batch = [node(Label.JSON, json), node(Label.SECCION, section)]
    relation = [link(RelationshipType.TIENE_SECCION, (Label.JSON, json), (Label.SECCION, section))]
    repository.write_batch(batch, relation, None)
    repository.write_batch(batch, relation, None)
    assert len(repository.node_relationships(Label.JSON, json)) == 1


def test_a_relationship_without_an_end_writes_nothing(real_graph: GraphAdapter, test_prefix: str) -> None:
    repository = PiaaRepository(real_graph)
    json, missing = f"{test_prefix}-j", f"{test_prefix}-missing"
    with pytest.raises(BatchError, match="doesn't exist"):
        repository.write_batch(
            [node(Label.JSON, json)],
            [link(RelationshipType.TIENE_SECCION, (Label.JSON, json), (Label.SECCION, missing))],
            None,
        )
    assert not exists(real_graph, Label.JSON, json)


def test_an_embeddings_experiment_takes_only_its_vectors_and_a_chunking_one_takes_all(
    real_graph: GraphAdapter, test_prefix: str
) -> None:
    """Feature 055: two embeddings experiments over the same chunk; replace_from one of them leaves the other's
    EXP_EMBED, and replace_from the chunking EXPERIMENTO takes the chunk with every vector."""
    L, T, p = Label, RelationshipType, test_prefix
    repository = PiaaRepository(real_graph)
    repository.write_batch(
        [
            node(L.EXPERIMENTO, p + "x"),
            node(L.EXP_DOCUMENTO, p + "x:d"),
            node(L.EXP_SECCION, p + "s"),
            node(L.EXP_CHUNK, p + "c"),
            node(L.EXP_EMBEDDINGS, p + "e1"),
            node(L.EXP_EMBEDDINGS, p + "e2"),
            node(L.EXP_EMBED, p + "e1:c"),
            node(L.EXP_EMBED, p + "e2:c"),
        ],
        [
            link(T.EXP_TIENE_DOCUMENTO, (L.EXPERIMENTO, p + "x"), (L.EXP_DOCUMENTO, p + "x:d")),
            link(T.EXP_TIENE_SECCION, (L.EXP_DOCUMENTO, p + "x:d"), (L.EXP_SECCION, p + "s")),
            link(T.EXP_TIENE_CHUNK, (L.EXP_SECCION, p + "s"), (L.EXP_CHUNK, p + "c")),
            link(T.EXP_USA, (L.EXP_EMBEDDINGS, p + "e1"), (L.EXPERIMENTO, p + "x")),
            *(link(T.EXP_TIENE_VECTOR, (L.EXP_CHUNK, p + "c"), (L.EXP_EMBED, f"{p}{e}:c")) for e in ("e1", "e2")),
            *(link(T.EXP_GENERA_VECTOR, (L.EXP_EMBEDDINGS, p + e), (L.EXP_EMBED, f"{p}{e}:c")) for e in ("e1", "e2")),
        ],
        None,
    )
    assert repository.write_batch([], [], NodeRef(L.EXP_EMBEDDINGS, p + "e1")).deleted == 1
    assert not exists(real_graph, L.EXP_EMBED, p + "e1:c") and exists(real_graph, L.EXP_EMBED, p + "e2:c")
    assert exists(real_graph, L.EXPERIMENTO, p + "x") and exists(real_graph, L.EXP_CHUNK, p + "c")
    assert repository.write_batch([], [], NodeRef(L.EXPERIMENTO, p + "x")).deleted == 4
    assert not exists(real_graph, L.EXP_EMBED, p + "e2:c") and exists(real_graph, L.EXP_EMBEDDINGS, p + "e2")
