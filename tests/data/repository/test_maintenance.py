"""VectorMigration (feature 055): over a graph that answers what each test scripts, and against a real Neo4j."""

import time
from collections.abc import Sequence
from contextlib import AbstractContextManager
from typing import LiteralString

import pytest

from data.models import GraphAdapter, GraphRow, GraphTransaction, Label, Parameters
from data.repository import VectorMigration, VectorNaming


def _property(model: str, dimensions: int) -> str:
    return f"embedding_{model.rsplit('/', 1)[-1].replace('-', '_')}_{dimensions}"


def _index(label: Label, property: str) -> str:
    return "vec_" + label.value.lower() + "_" + property.removeprefix("embedding_")


NAMING = VectorNaming(_property, _index, "org/mini", {"org/mini": 3})


class _Script(GraphAdapter):
    """Answers each query by the first fragment of the script it contains; records every write."""

    def __init__(self, answers: Sequence[tuple[str, list[GraphRow]]]) -> None:
        self._answers = list(answers)
        self.writes: list[tuple[str, Parameters]] = []

    def verify(self) -> None:
        pass

    def _answer(self, cypher: str) -> list[GraphRow]:
        for fragment, rows in self._answers:
            if fragment in cypher:
                return rows
        return []

    def read(self, cypher: LiteralString, parameters: Parameters | None = None) -> list[GraphRow]:
        return self._answer(cypher)

    def write(self, cypher: LiteralString, parameters: Parameters | None = None) -> list[GraphRow]:
        self.writes.append((cypher, parameters or {}))
        return self._answer(cypher)

    def transaction(self) -> AbstractContextManager[GraphTransaction]:
        raise AssertionError("the migration uses no explicit transaction")

    def close(self) -> None:
        pass


type Script = list[tuple[str, list[GraphRow]]]

LEGACY: Script = [("properties[0] = 'embedding'", [{"name": "vec_fragmentos_mini_3"}])]
FRAGMENTS: Script = [
    ("MATCH (f:FRAGMENTOS) WHERE f.embedding IS NOT NULL\nRETURN", [{"model": "org/mini", "dimensions": 3, "nodes": 2}])
]
DOCUMENTS: Script = [
    ("MATCH (j:JSON) WHERE j.huella_embedding IS NOT NULL\nRETURN", [{"model": "org/mini", "nodes": 1}])
]
ORPHANS: Script = [("RETURN count(*) AS nodes", [{"nodes": 0}])]


def test_a_simulation_counts_and_writes_nothing() -> None:
    graph = _Script([*LEGACY, *FRAGMENTS, *DOCUMENTS, *ORPHANS])
    report = VectorMigration(graph, NAMING).run(simulate=True)
    assert graph.writes == []
    assert [(g.property, g.nodes) for g in report.fragments] == [("embedding_mini_3", 2)]
    assert [(g.property, g.nodes) for g in report.documents] == [("embedding_mini_3", 1)]
    assert report.dropped_indexes == ["vec_fragmentos_mini_3"]
    assert report.created_indexes == ["vec_fragmentos_mini_3"]  # the same name, on the new property


def test_the_old_indexes_go_before_any_vector_moves() -> None:
    graph = _Script([*LEGACY, *FRAGMENTS, *ORPHANS])
    VectorMigration(graph, NAMING).run()
    assert graph.writes[0] == ("DROP INDEX $name IF EXISTS", {"name": "vec_fragmentos_mini_3"})
    assert "SET f.`embedding_mini_3` = f.embedding" in graph.writes[1][0]


def test_the_fingerprints_go_to_their_model_keys() -> None:
    graph = _Script([*DOCUMENTS, *ORPHANS])
    VectorMigration(graph, NAMING).run()
    [(_, parameters)] = [w for w in graph.writes if "j[$fingerprint]" in w[0]]
    assert (parameters["fingerprint"], parameters["limit"]) == (
        "huella_embedding_mini_3",
        "limite_tokens_embedding_mini_3",
    )


def test_the_fingerprints_of_a_model_without_known_dimensions_stay() -> None:
    unknown: Script = [("MATCH (j:JSON) WHERE j.huella_embedding IS NOT NULL\nRETURN", [{"model": "x/y", "nodes": 4}])]
    graph = _Script([*unknown, *ORPHANS])
    report = VectorMigration(graph, NAMING).run()
    assert report.unknown_documents == 4 and not [w for w in graph.writes if "j[$fingerprint]" in w[0]]


def test_nothing_to_move_is_nothing_pending() -> None:
    assert not VectorMigration(_Script([*ORPHANS]), NAMING).run().pending


# Against a real Neo4j: the old shape in, the new one out, twice.


def _wait(graph: GraphAdapter, index: str) -> None:
    for _ in range(100):
        if graph.read(
            "SHOW VECTOR INDEXES YIELD name, state WHERE name = $n AND state = 'ONLINE' RETURN 1", {"n": index}
        ):
            return
        time.sleep(0.1)


@pytest.mark.neo4j
def test_a_real_graph_is_migrated_once(real_graph: GraphAdapter, test_prefix: str) -> None:
    if real_graph.read("SHOW VECTOR INDEXES YIELD name RETURN name"):
        pytest.skip("this Neo4j already has vector indexes: the migration would touch them")
    p = test_prefix
    real_graph.write(
        "CREATE (j:JSON {id: $p + 'j', estado_chunking: 'fragmentado', huella_embedding: 'sha256:h',"
        "  modelo_embedding: 'org/mini', limite_tokens_embedding: 128})-[:TIENE_SECCION]->(s:SECCION {id: $p + 's'}),"
        " (s)-[:TIENE_FRAGMENTO]->(:FRAGMENTOS {id: $p + 'f', texto: 'uno', embedding: [1.0, 0.0, 0.0],"
        "  modelo_embedding: 'org/mini', version_embedding: 1}),"
        " (e:EXP_EMBEDDINGS {id: $p + 'e'}),"
        " (x:EXP_SECCION {id: $p + 'x', sha256: $p + 'j'})-[:EXP_TIENE_CHUNK]->(:EXP_CHUNK {id: $p + 'c', texto: 'a',"
        "  embedding: [0.0, 1.0, 0.0], modelo_embedding: 'org/mini', version_embedding: 1,"
        "  experimento_embedding: $p + 'e'}),"
        " (x)-[:EXP_TIENE_CHUNK]->(:EXP_CHUNK {id: $p + 'o', texto: 'b', embedding: [0.0, 0.0, 1.0],"
        "  experimento_embedding: $p + 'gone'})",
        {"p": p},
    )
    real_graph.write(
        "CREATE VECTOR INDEX vec_fragmentos_mini_3 FOR (n:FRAGMENTOS) ON n.embedding"
        " OPTIONS { indexConfig: { `vector.dimensions`: 3, `vector.similarity_function`: 'cosine' } }"
    )
    try:
        assert VectorMigration(real_graph, NAMING).run(simulate=True).fragments[0].nodes == 1
        report = VectorMigration(real_graph, NAMING).run()
        assert report.dropped_indexes == ["vec_fragmentos_mini_3"]
        assert sorted(report.created_indexes) == ["vec_exp_embed_mini_3", "vec_fragmentos_mini_3"]
        assert report.orphan_vectors == 1
        [f] = real_graph.read("MATCH (f:FRAGMENTOS {id: $id}) RETURN properties(f) AS p", {"id": p + "f"})
        assert f["p"] == {"id": p + "f", "texto": "uno", "embedding_mini_3": [1.0, 0.0, 0.0]}
        [j] = real_graph.read("MATCH (j:JSON {id: $id}) RETURN properties(j) AS p", {"id": p + "j"})
        assert j["p"] == {
            "id": p + "j",
            "estado_chunking": "fragmentado",
            "huella_embedding_mini_3": "sha256:h",
            "limite_tokens_embedding_mini_3": 128,
        }
        [v] = real_graph.read(
            "MATCH (c:EXP_CHUNK {id: $c})-[:EXP_TIENE_VECTOR]->(v:EXP_EMBED)<-[:EXP_GENERA_VECTOR]-(:EXP_EMBEDDINGS)"
            " RETURN v.id AS id, v.embedding_mini_3 AS vector, c.embedding AS old, c.experimento_embedding AS owner",
            {"c": p + "c"},
        )
        assert v == {"id": p + "e:" + p + "c", "vector": [0.0, 1.0, 0.0], "old": None, "owner": None}
        [o] = real_graph.read("MATCH (c:EXP_CHUNK {id: $c}) RETURN c.embedding AS old", {"c": p + "o"})
        assert o["old"] is None
        _wait(real_graph, "vec_exp_embed_mini_3")
        again = VectorMigration(real_graph, NAMING).run()
        assert not again.pending  # idempotent
    finally:
        for index in ("vec_fragmentos_mini_3", "vec_exp_embed_mini_3"):
            real_graph.write("DROP INDEX $name IF EXISTS", {"name": index})
        real_graph.write("MATCH (v:EXP_EMBED) WHERE v.id STARTS WITH $p DETACH DELETE v", {"p": p})
