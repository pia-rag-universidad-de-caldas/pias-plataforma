"""ExperimentMigration (feature 055 part b): over a graph that answers what each test scripts, and against a real
Neo4j."""

from collections.abc import Sequence
from contextlib import AbstractContextManager
from typing import LiteralString

import pytest

from data.models import GraphAdapter, GraphRow, GraphTransaction, Label, Parameters
from data.repository import ExperimentMigration
from data.repository.experiment_migration import BATCH


class _Script(GraphAdapter):
    """Answers each query by the first fragment of the script it contains (a list of answers is used up in order);
    records every write."""

    def __init__(self, answers: Sequence[tuple[str, list[list[GraphRow]]]]) -> None:
        self._answers = [(fragment, list(rows)) for fragment, rows in answers]
        self.writes: list[str] = []

    def verify(self) -> None:
        pass

    def _answer(self, cypher: str) -> list[GraphRow]:
        for fragment, answers in self._answers:
            if fragment in cypher:
                return answers.pop(0) if len(answers) > 1 else answers[0]
        return []

    def read(self, cypher: LiteralString, parameters: Parameters | None = None) -> list[GraphRow]:
        return self._answer(cypher)

    def write(self, cypher: LiteralString, parameters: Parameters | None = None) -> list[GraphRow]:
        self.writes.append(cypher)
        return self._answer(cypher)

    def transaction(self) -> AbstractContextManager[GraphTransaction]:
        raise AssertionError("the migration uses no explicit transaction")

    def close(self) -> None:
        pass


type Script = list[tuple[str, list[list[GraphRow]]]]


def _nodes(n: int) -> list[list[GraphRow]]:
    return [[{"nodes": n}]]


COUNTS: Script = [
    ("RETURN count(u) AS nodes", _nodes(2)),
    ("RETURN count(g) AS nodes", _nodes(3)),
    ("RETURN count(d) AS nodes", _nodes(1)),
    ("RETURN count(s) AS nodes", _nodes(0)),
    ("RETURN count(p) AS nodes", _nodes(4)),
    ("RETURN DISTINCT e.id AS id", [[{"id": "old"}]]),
]


def test_a_simulation_counts_and_writes_nothing() -> None:
    graph = _Script(COUNTS)
    report = ExperimentMigration(graph).run(simulate=True)
    assert graph.writes == []
    assert (report.documents, report.sections, report.old_documents, report.orphan_sections, report.scores) == (
        2,
        3,
        1,
        0,
        4,
    )
    assert report.legacy_experiments == ["old"] and report.pending


def test_the_new_shape_is_written_before_anything_is_deleted() -> None:
    graph = _Script(COUNTS)
    ExperimentMigration(graph).run()
    steps = graph.writes
    assert "EXP_TIENE_DOCUMENTO" in steps[0] and "DELETE u" in steps[0]  # summaries to their EXP_DOCUMENTO
    assert "EXP_TIENE_SECCION" in steps[1] and "DELETE g" in steps[1]  # the sections under them
    assert [("DETACH DELETE" in step) for step in steps] == [False, False, True, True, True]


def test_each_step_goes_on_until_a_batch_comes_back_short() -> None:
    graph = _Script([("DELETE u", [[{"moved": BATCH}], [{"moved": BATCH}], [{"moved": 3}]])])
    ExperimentMigration(graph).run()
    assert sum("DELETE u" in w for w in graph.writes) == 3


def test_a_migrated_graph_has_nothing_pending() -> None:
    report = ExperimentMigration(_Script([])).run()
    assert not report.pending and report.legacy_experiments == []


# Against a real Neo4j (NEO4J_TEST_URL): the migration runs over the whole test database, so these tests only look at
# their own ids (their prefix) and leave the rest as the migration leaves it.


def _exists(graph: GraphAdapter, label: Label, id: str) -> bool:
    return bool(graph.read("MATCH (n {id: $id}) WHERE $label IN labels(n) RETURN n.id", {"id": id, "label": label}))


@pytest.mark.neo4j
def test_an_experiment_of_043_gets_its_documents_and_twice_changes_nothing(
    real_graph: GraphAdapter, test_prefix: str
) -> None:
    p = test_prefix
    real_graph.write(
        "CREATE (e:EXPERIMENTO {id: $p + 'x'}), (j:JSON {id: $p + 'j'}), "
        "(e)-[:EXP_USA {sha256: $p + 'j', estado: 'fragmentado', chunks: 1}]->(j), "
        "(s:EXP_SECCION {id: $p + 'x:j:s0', sha256: $p + 'j'}), (e)-[:EXP_GENERA]->(s), "
        "(c:EXP_CHUNK {id: $p + 'x:j:0'}), (s)-[:EXP_TIENE_CHUNK]->(c), "
        "(old:EXP_DOCUMENTO {id: $p + 'old'}), (os:EXP_SECCION {id: $p + 'old:s0'}), "
        "(old)-[:EXP_TIENE_SECCION]->(os), (lost:EXP_SECCION {id: $p + 'lost'}), "
        "(score:EXP_PUNTUACION {id: $p + 'score'})",
        {"p": p},
    )
    ExperimentMigration(real_graph).run()
    rows = real_graph.read(
        "MATCH (:EXPERIMENTO {id: $p + 'x'})-[:EXP_TIENE_DOCUMENTO]->(d:EXP_DOCUMENTO)"
        "-[:EXP_DE]->(:JSON {id: $p + 'j'}) "
        "MATCH (d)-[:EXP_TIENE_SECCION]->(:EXP_SECCION)-[:EXP_TIENE_CHUNK]->(:EXP_CHUNK {id: $p + 'x:j:0'}) "
        "RETURN d.id AS id, d.chunks AS chunks, d.estado AS estado",
        {"p": p},
    )
    assert rows == [{"id": p + "x:" + p + "j", "chunks": 1, "estado": "fragmentado"}]
    assert not real_graph.read("MATCH (:EXPERIMENTO {id: $p + 'x'})-[r:EXP_USA|EXP_GENERA]->() RETURN r", {"p": p})
    for gone in ("old", "old:s0", "lost", "score"):
        assert not real_graph.read("MATCH (n {id: $id}) RETURN n", {"id": p + gone})
    assert _exists(real_graph, Label.JSON, p + "j")  # the official document stays
    ExperimentMigration(real_graph).run()  # a second run: the same graph
    assert real_graph.read("MATCH (d:EXP_DOCUMENTO) WHERE d.id STARTS WITH $p RETURN d.id AS id", {"p": p}) == [
        {"id": p + "x:" + p + "j"}
    ]
