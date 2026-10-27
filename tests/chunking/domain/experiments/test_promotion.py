"""Promotion (feature 028): the batches that copy an approved experiment to the official graph."""

import pytest

from chunking.domain import Promotion
from chunking.models import (
    CONVERTED,
    ChunkPiece,
    ConversionProperties,
    DocumentError,
    ExperimentSection,
    GraphLabel,
    GraphRelation,
    NodeKey,
    NodeWrite,
)

SHA = "ab" * 32


def stored(code: str = "020055", status: str = CONVERTED) -> ConversionProperties:
    return {
        "sha256": SHA,
        "origen": "2024/a.pdf",
        "destino": "v/a.pdf",
        "nombre": "a.pdf",
        "tipo": "pdf",
        "anio": 2024,
        "codigo": code,
        "conversion": "{}",
        "fingerprint_conversion": "f1",
        "docling": "2",
        "estado": status,
        "error": None,
        "contenido": '{"titulo": "", "secciones": []}',
        "secciones": 0,
        "duracion_conversion": 1.0,
        "convertido_en": "2026-01-01",
    }


def test_conversion_becomes_the_official_json_of_its_piaa() -> None:
    batch = Promotion.conversion(stored(), f"{SHA}:f1", "exp1", "now")
    root = NodeKey(GraphLabel.JSON, SHA)
    assert batch.replace_from == root
    assert [(n.key, n.mode) for n in batch.nodes] == [
        (NodeKey(GraphLabel.PIAA, "020055"), NodeWrite.ENSURE),
        (root, NodeWrite.REPLACE),
    ]
    assert batch.nodes[1].properties["estado"] == "convertido"
    assert [(link.type, link.target) for link in batch.links] == [
        (GraphRelation.ES, root),
        (GraphRelation.VIENE_DE, NodeKey(GraphLabel.EXP_DOCUMENTO, f"{SHA}:f1")),
    ]


def test_unassigned_code_gets_no_piaa() -> None:
    batch = Promotion.conversion(stored("000000"), f"{SHA}:f1", "exp1", "now")
    assert [n.key.label for n in batch.nodes] == [GraphLabel.JSON]


def test_a_failed_conversion_is_not_promoted() -> None:
    with pytest.raises(DocumentError):
        Promotion.conversion(stored(status="error"), f"{SHA}:f1", "exp1", "now")


def test_chunks_go_under_the_official_json_with_its_ids() -> None:
    sections = [ExperimentSection(0, "Objetivos", 1, [1], None, "points", "{}", 2, 10)]
    chunks = [(0, ChunkPiece("a", ["Objetivos"], [1], 4)), (0, ChunkPiece("b", ["Objetivos"], [1], 6))]
    batch = Promotion.chunks(SHA, sections, chunks, "exp2", "now")
    root = NodeKey(GraphLabel.JSON, SHA)
    assert batch.replace_from == root
    assert batch.nodes[0].key == root and batch.nodes[0].mode == NodeWrite.MERGE
    assert batch.nodes[0].properties["fragmentos"] == 2
    assert [n.key.id for n in batch.nodes[1:]] == [f"{SHA}:s0", f"{SHA}:0", f"{SHA}:1"]
    assert batch.nodes[1].properties["regla"] == "default"
    assert [link.type for link in batch.links] == [GraphRelation.TIENE_SECCION] + [GraphRelation.TIENE_FRAGMENTO] * 2


def test_a_chunk_of_a_missing_section_fails_the_document() -> None:
    with pytest.raises(DocumentError):
        Promotion.chunks(SHA, [], [(3, ChunkPiece("a", [], [], 1))], "exp2", "now")
