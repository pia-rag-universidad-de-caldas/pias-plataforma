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
