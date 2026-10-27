"""The stored shapes (feature 027): the rule format and the experiment mappers that read them back."""

import pytest

from chunking.adapters.data import experiment_mappers as to
from chunking.adapters.data.mappers import processed, stored
from chunking.domain import ExperimentGraph, Hierarchy
from chunking.models import (
    Chunk,
    ChunkedDocument,
    ChunkingParameters,
    ConversionParameters,
    DocumentStatus,
    GraphLabel,
    Inclusion,
    JsonProperties,
    Score,
    SourceDocument,
    TableMode,
    rule_index,
    rule_name,
)

PARAMETERS = ChunkingParameters("tok", 512, True, False, True, TableMode.ACCURATE, "2.134.0")
CONVERSION = ConversionParameters(1, False, True, TableMode.ACCURATE, Inclusion(), "2.134.0")
DOCUMENT = SourceDocument("2024/a.pdf", "vigentes/pdf/a.pdf", "a.pdf", "ab" * 32, "pdf", 2024, "020055")


@pytest.mark.parametrize("rule", [None, 0, 3])
def test_rule_name_goes_back_with_rule_index(rule: int | None) -> None:
    assert rule_index(rule_name(rule)) == rule


def test_rule_name_is_the_stored_text() -> None:
    assert (rule_name(None), rule_name(1)) == ("default", "1")
    assert rule_index("otra") is None


def test_stored_reads_a_missing_key_as_none() -> None:
    p = stored({"fragmentos": 3}, JsonProperties)
    read: list[object] = [p["fragmentos"], p["origen"]]  # typed as the shape says, but data may lack a key
    assert read == [3, None]


def test_what_hierarchy_writes_is_what_the_mapper_reads() -> None:
    chunk = Chunk(0, "t", "h t", ["h"], [1], 3)
    batch = Hierarchy.build(DOCUMENT, ChunkedDocument([chunk]), PARAMETERS, "2026-10-22T00:00:00")
    node = next(n for n in batch.nodes if n.key.label == GraphLabel.JSON)
    document = processed({"id": node.key.id, "properties": dict(node.properties)})
    assert document is not None
    assert (document.origin, document.status, document.chunks) == ("2024/a.pdf", DocumentStatus.CHUNKED, 1)
    assert document.parameters == PARAMETERS


def test_experiment_document_status_is_closed() -> None:
    use = {"sha256": "ab" * 32, "estado": "fragmentado", "reutilizado": True, "secciones": 2, "chunks": 5}
    assert to.document("ab" * 32 + ":f", use).status is DocumentStatus.CHUNKED
    assert to.document("ab" * 32 + ":f", {**use, "estado": "raro"}).status is DocumentStatus.ERROR


def test_experiment_section_rule_is_an_index_or_none() -> None:
    section = {"indice": 2, "titulo": "Objetivos", "regla": "1", "estrategia": "points", "chunks": 3}
    assert to.section(2, section).rule == 1
    assert to.section(2, {**section, "regla": "default"}).rule is None


def test_a_score_goes_and_comes_back() -> None:
    score = Score("s1", {"coherencia": 4.0}, "2026-01-01", "2026-01-02", "analista", None, None)
    assert to.score(dict(to.score_properties("e1", score))) == score


def test_the_conversion_states_are_shared() -> None:
    batch = ExperimentGraph.conversion(DOCUMENT, "ab" * 32, CONVERSION, None, "boom", 1.0, "2026-01-01")
    assert to.conversion(dict(batch.nodes[0].properties))["estado"] == "error"
