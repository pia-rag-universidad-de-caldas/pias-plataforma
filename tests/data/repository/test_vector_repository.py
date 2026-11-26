"""VectorRepository against a real Neo4j (features 046 and 055): the index, its repetition and the search."""

import time

import pytest

from data.models import GraphAdapter, Label
from data.repository import PiaaRepository
from data.repository.vector_repository import VectorIndexConflict, VectorRepository

pytestmark = pytest.mark.neo4j


def _index(prefix: str) -> str:
    return "vec_test_" + prefix.rsplit("-", 1)[-1][:16]


def _property(prefix: str) -> str:
    """A vector property of its own per test: an index on it can't collide with anyone's."""
    return "embedding_test_" + prefix.rsplit("-", 1)[-1][:16]


def test_an_index_is_created_once_and_a_different_one_is_a_conflict(real_graph: GraphAdapter, test_prefix: str) -> None:
    name, vectors, property = _index(test_prefix), VectorRepository(real_graph), _property(test_prefix)
    try:
        assert vectors.ensure(name, Label.FRAGMENTOS, property, 3)["dimensions"] == 3
        assert vectors.ensure(name, Label.FRAGMENTOS, property, 3) == vectors.find(name)  # repeating changes nothing
        with pytest.raises(VectorIndexConflict):
            vectors.ensure(name, Label.FRAGMENTOS, property, 4)
        with pytest.raises(VectorIndexConflict, match="one per label"):  # another index on the same property
            vectors.ensure(name + "_other", Label.FRAGMENTOS, property, 3)
        assert vectors.drop(name) == 0 and vectors.drop(name) is None
    finally:
        real_graph.write("DROP INDEX $name IF EXISTS", {"name": name})


def test_two_models_have_an_index_each_on_the_same_label(real_graph: GraphAdapter, test_prefix: str) -> None:
    name, vectors, property = _index(test_prefix), VectorRepository(real_graph), _property(test_prefix)
    try:
        vectors.ensure(name + "_a", Label.FRAGMENTOS, property + "_a", 3)
        assert vectors.ensure(name + "_b", Label.FRAGMENTOS, property + "_b", 5)["dimensions"] == 5
    finally:
        for index in (name + "_a", name + "_b"):
            real_graph.write("DROP INDEX $name IF EXISTS", {"name": index})


def test_dropping_an_index_with_its_property_removes_only_that_model(
    real_graph: GraphAdapter, test_prefix: str
) -> None:
    name, vectors, p = _index(test_prefix), VectorRepository(real_graph), test_prefix
    property = _property(p)
    real_graph.write(
        "CREATE (f:FRAGMENTOS {id: $p + 'f', texto: 'uno'}) SET f[$a] = [1.0, 0.0], f[$b] = [0.0, 1.0]",
        {"p": p, "a": property + "_a", "b": property + "_b"},
    )
    try:
        vectors.ensure(name, Label.FRAGMENTOS, property + "_a", 2)
        node = PiaaRepository(real_graph).node(Label.FRAGMENTOS, p + "f", ["embedding"])
        assert node is not None and node.properties == {"texto": "uno"}  # ?omit=embedding: every vector
        assert vectors.drop(name, drop_property=True) == 1
        [row] = real_graph.read("MATCH (f:FRAGMENTOS {id: $id}) RETURN keys(f) AS keys", {"id": p + "f"})
        keys = row["keys"]
        assert isinstance(keys, list) and sorted(str(k) for k in keys) == sorted(["id", "texto", property + "_b"])
    finally:
        real_graph.write("DROP INDEX $name IF EXISTS", {"name": name})


def test_the_search_finds_only_chunks_of_chunked_documents(real_graph: GraphAdapter, test_prefix: str) -> None:
    name, vectors, p = _index(test_prefix), VectorRepository(real_graph), test_prefix
    property = _property(p)
    real_graph.write(
        "CREATE (j:JSON {id: $p + 'j', estado_chunking: 'fragmentado'})-[:TIENE_SECCION]->(s:SECCION {id: $p + 's'}),"
        " (s)-[:TIENE_FRAGMENTO]->(f:FRAGMENTOS {id: $p + 'f', texto: 'uno'}),"
        " (j)-[:VIENE_DE]->(:RAW {id: $p + 'j', origen: 'a/b.pdf', codigo: '020055'}),"
        " (k:JSON {id: $p + 'k', estado_chunking: 'error'})-[:TIENE_SECCION]->(t:SECCION {id: $p + 't'}),"
        " (t)-[:TIENE_FRAGMENTO]->(g:FRAGMENTOS {id: $p + 'g', texto: 'dos'})"
        " SET f[$v] = [1.0, 0.0, 0.0], g[$v] = [1.0, 0.0, 0.0]",
        {"p": p, "v": property},
    )
    try:
        vectors.ensure(name, Label.FRAGMENTOS, property, 3)
        for _ in range(50):  # the index is filled in the background
            found = vectors.search(name, [1.0, 0.0, 0.0], 5)
            if found:
                break
            time.sleep(0.2)
        assert [(row["id"], row["origin"], row["code"]) for row in found] == [(p + "f", "a/b.pdf", "020055")]
    finally:
        real_graph.write("DROP INDEX $name IF EXISTS", {"name": name})


def test_the_search_of_an_experiment_finds_only_its_chunks(real_graph: GraphAdapter, test_prefix: str) -> None:
    """Two embeddings experiments over the same chunk: each one has its EXP_EMBED, and finds only its own."""
    name, vectors, p = _index(test_prefix), VectorRepository(real_graph), test_prefix
    property = _property(p)
    real_graph.write(
        "CREATE (s:EXP_SECCION {id: $p + 's', sha256: $p + 'h'}),"
        " (s)-[:EXP_TIENE_CHUNK]->(c1:EXP_CHUNK {id: $p + 'c1', texto: 'uno', encabezados: ['t'], paginas: [2]}),"
        " (s)-[:EXP_TIENE_CHUNK]->(c2:EXP_CHUNK {id: $p + 'c2', texto: 'dos'}),"
        " (e1:EXP_EMBEDDINGS {id: $p + 'e1'}), (e2:EXP_EMBEDDINGS {id: $p + 'e2'}),"
        " (c1)-[:EXP_TIENE_VECTOR]->(v1:EXP_EMBED {id: $p + 'e1:c1'})<-[:EXP_GENERA_VECTOR]-(e1),"
        " (c1)-[:EXP_TIENE_VECTOR]->(v2:EXP_EMBED {id: $p + 'e2:c1'})<-[:EXP_GENERA_VECTOR]-(e2),"
        " (c2)-[:EXP_TIENE_VECTOR]->(v3:EXP_EMBED {id: $p + 'e2:c2'})<-[:EXP_GENERA_VECTOR]-(e2),"
        " (:RAW {id: $p + 'h', origen: 'a/b.pdf', codigo: '020055'})"
        " SET v1[$v] = [1.0, 0.0, 0.0], v2[$v] = [1.0, 0.0, 0.0], v3[$v] = [1.0, 0.0, 0.0]",
        {"p": p, "v": property},
    )
    try:
        vectors.ensure(name, Label.EXP_EMBED, property, 3)
        for _ in range(50):  # the index is filled in the background
            found = vectors.search_experiment(name, [1.0, 0.0, 0.0], 5, p + "e1")
            if found:
                break
            time.sleep(0.2)
        assert [(r["id"], r["sha256"], r["origin"], r["code"], r["pages"]) for r in found] == [
            (p + "c1", p + "h", "a/b.pdf", "020055", [2])
        ]
        assert sorted(str(r["id"]) for r in vectors.search_experiment(name, [1.0, 0.0, 0.0], 5, p + "e2")) == [
            p + "c1",
            p + "c2",
        ]
        assert vectors.search_experiment(name, [1.0, 0.0, 0.0], 5, p + "none") == []
    finally:
        real_graph.write("DROP INDEX $name IF EXISTS", {"name": name})
