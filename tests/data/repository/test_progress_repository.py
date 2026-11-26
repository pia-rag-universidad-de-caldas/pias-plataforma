"""ProgressRepository against a real Neo4j (features 042 and 043): the counts move by what the test writes, so it can
share a database with other data (only its prefix is written and deleted)."""

import pytest

from data.models import GraphAdapter
from data.repository.progress_repository import ProgressRepository

pytestmark = pytest.mark.neo4j


def _write(graph: GraphAdapter, prefix: str) -> None:
    graph.write(
        """
        CREATE (:RAW {id: $p + 'a', vigente: true, estado_parseo: 'parseado', fingerprint_parseo: 'f1'})
        CREATE (:RAW {id: $p + 'b', vigente: true, estado_parseo: 'parseado', fingerprint_parseo: 'f0'})
        CREATE (:RAW {id: $p + 'c', vigente: true, estado_parseo: 'parcial'})
        CREATE (:RAW {id: $p + 'd', vigente: true})
        CREATE (:RAW {id: $p + 'e', vigente: false, estado_parseo: 'error'})
        CREATE (:JSON {id: $p + 'a', estado: 'parseado', estado_chunking: 'fragmentado', fingerprint_parseo: 'f1',
                       config_chunking: 'c1', parseo_chunkeado: 'f1'})
        CREATE (:JSON {id: $p + 'z', estado: 'parseado', estado_chunking: 'fragmentado', fingerprint_parseo: 'f2',
                       config_chunking: 'c1', parseo_chunkeado: 'f1'})
        CREATE (:JSON {id: $p + 'b', estado: 'parseado', estado_chunking: 'error'})
        CREATE (:JSON {id: $p + 'c', estado: 'parcial'})
        """,
        {"p": prefix},
    )


def _delta(after: dict[str, int], before: dict[str, int]) -> dict[str, int]:
    return {key: after[key] - before[key] for key in after}


def test_parsing_counts_the_current_raw_and_the_fingerprint(real_graph: GraphAdapter, test_prefix: str) -> None:
    progress = ProgressRepository(real_graph)
    before, before_f1 = progress.parsing_counts(None), progress.parsing_counts("f1")
    _write(real_graph, test_prefix)
    assert _delta(progress.parsing_counts(None), before) == {
        "total": 4,
        "done": 2,
        "partial": 1,
        "errors": 0,
        "never": 1,
    }
    assert _delta(progress.parsing_counts("f1"), before_f1)["done"] == 1  # b has another fingerprint
    missing = progress.parsing_ids(False, "f1", 0, 10_000)
    assert {f"{test_prefix}{x}" for x in "bcd"} <= set(missing) and f"{test_prefix}a" not in missing


def test_chunking_counts_the_parsed_json(real_graph: GraphAdapter, test_prefix: str) -> None:
    progress = ProgressRepository(real_graph)
    before = progress.chunking_counts()
    _write(real_graph, test_prefix)
    assert _delta(progress.chunking_counts(), before) == {"total": 4, "done": 2, "partial": 0, "errors": 1, "never": 1}
    done = progress.chunking_ids(True, None, 0, 10_000)
    assert f"{test_prefix}a" in done and f"{test_prefix}b" not in done


def test_chunking_with_a_fingerprint_counts_only_that_configuration_over_the_current_parse(
    real_graph: GraphAdapter, test_prefix: str
) -> None:
    progress = ProgressRepository(real_graph)
    before = progress.chunking_counts("c1")
    _write(real_graph, test_prefix)
    assert _delta(progress.chunking_counts("c1"), before)["done"] == 1  # z was chunked over an older parse
    done = progress.chunking_ids(True, "c1", 0, 10_000)
    assert f"{test_prefix}a" in done and f"{test_prefix}z" not in done
    assert f"{test_prefix}a" not in progress.chunking_ids(True, "c2", 0, 10_000)


def test_listing_all_takes_the_done_and_the_missing_ones(real_graph: GraphAdapter, test_prefix: str) -> None:
    _write(real_graph, test_prefix)
    every = ProgressRepository(real_graph).chunking_ids(None, None, 0, 10_000)
    assert {f"{test_prefix}{x}" for x in "abcz"} <= set(every)  # chunked, in error and never chunked
    assert every == sorted(every)


def test_an_embeddings_experiment_misses_the_documents_without_its_vectors(
    real_graph: GraphAdapter, test_prefix: str
) -> None:
    real_graph.write(
        """
        CREATE (x:EXP_EMBEDDINGS {id: $p + 'x'})-[:EXP_USA]->(e:EXPERIMENTO {id: $p + 'e'})
        CREATE (e)-[:EXP_TIENE_DOCUMENTO]->(a:EXP_DOCUMENTO {id: $p + 'e:a', sha256: 'a', estado: 'fragmentado'})
        CREATE (e)-[:EXP_TIENE_DOCUMENTO]->(b:EXP_DOCUMENTO {id: $p + 'e:b', sha256: 'b', estado: 'fragmentado'})
        CREATE (e)-[:EXP_TIENE_DOCUMENTO]->(:EXP_DOCUMENTO {id: $p + 'e:c', sha256: 'c', estado: 'error'})
        CREATE (a)-[:EXP_TIENE_SECCION]->(sa:EXP_SECCION {id: $p + 'sa'})
        CREATE (sa)-[:EXP_TIENE_CHUNK]->(ca:EXP_CHUNK {id: $p + 'ca'})
        CREATE (b)-[:EXP_TIENE_SECCION]->(sb:EXP_SECCION {id: $p + 'sb'})
        CREATE (sb)-[:EXP_TIENE_CHUNK]->(:EXP_CHUNK {id: $p + 'cb'})
        CREATE (ca)-[:EXP_TIENE_VECTOR]->(:EXP_EMBED {id: $p + 'v'})<-[:EXP_GENERA_VECTOR]-(x)
        """,
        {"p": test_prefix},
    )
    progress = ProgressRepository(real_graph)
    experiment = f"{test_prefix}x"
    assert progress.embeddings_experiment_exists(experiment)
    counts = progress.experiment_embedding_counts(experiment)
    assert counts == {"total": 2, "done": 1, "partial": 0, "errors": 0, "never": 1}
    assert progress.experiment_embedding_ids(False, experiment, 0, 10) == ["b"]
    assert progress.experiment_embedding_ids(None, experiment, 0, 10) == ["a", "b"]
