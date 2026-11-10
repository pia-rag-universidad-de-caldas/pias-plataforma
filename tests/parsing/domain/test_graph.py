"""ParsedGraph and the codec (feature 042): the batch of a parsed document and how its DoclingDocument is stored."""

from parsing.domain import ParsedGraph, decode, encode
from parsing.models import GraphLabel, GraphRelation, NodeKey, NodeWrite, PageCoverage, ParsedOutput, RawFile

RAW = RawFile("a" * 64, "plan.pdf", "pdf", "020055", b"%PDF")
DOCUMENT = {"schema_name": "DoclingDocument", "texts": [{"text": "Objetivos de la asignatura"}]}


def test_the_document_is_stored_compressed_and_comes_back_whole() -> None:
    text, size = encode(DOCUMENT)
    assert decode(text) == DOCUMENT and size > 0


def test_something_that_isnt_a_stored_document_decodes_to_none() -> None:
    assert decode("not base64!") is None


def test_a_parsed_document_hangs_from_its_piaa_and_comes_from_its_raw() -> None:
    batch = ParsedGraph.parsed(RAW, ParsedOutput(DOCUMENT, PageCoverage(2, 2), [2]), "f1", "2.148.0", "at", 1.25)
    json_key, raw_key = NodeKey(GraphLabel.JSON, RAW.sha256), NodeKey(GraphLabel.RAW, RAW.sha256)
    modes = {n.key: n.mode for n in batch.nodes}
    assert modes == {
        json_key: NodeWrite.REPLACE,
        raw_key: NodeWrite.MERGE,
        NodeKey(GraphLabel.PIAA, "020055"): NodeWrite.ENSURE,
    }
    assert {(link.type, link.target) for link in batch.links} == {
        (GraphRelation.VIENE_DE, raw_key),
        (GraphRelation.ES, json_key),
    }
    assert batch.replace_from == json_key  # the chunks of an earlier parsing go
    json = next(n.properties for n in batch.nodes if n.key == json_key)
    assert (json["estado"], json["paginas_ocr"], json["duracion_parseo"]) == ("parseado", [2], 1.2)
    assert decode(str(json["documento"])) == DOCUMENT


def test_a_partial_one_says_why_and_its_raw_too() -> None:
    output = ParsedOutput(DOCUMENT, PageCoverage(3, 2, [3], reason="timeout"))
    batch = ParsedGraph.parsed(RAW, output, "f1", "2", "at", 1.0)
    states = {n.key.label: n.properties for n in batch.nodes}
    assert (states[GraphLabel.JSON]["estado"], states[GraphLabel.JSON]["error"]) == ("parcial", "timeout")
    assert states[GraphLabel.RAW]["estado_parseo"] == "parcial"


def test_a_course_without_a_code_hangs_from_no_piaa() -> None:
    raw = RawFile("b" * 64, "x.docx", "docx", "000000", b"")
    batch = ParsedGraph.parsed(raw, ParsedOutput(DOCUMENT, PageCoverage()), "f1", "2", "at", 0.0)
    assert {n.key.label for n in batch.nodes} == {GraphLabel.JSON, GraphLabel.RAW}


def test_a_failure_only_touches_the_raw() -> None:
    batch = ParsedGraph.failed("a", "corrupt")
    assert [(n.key.label, n.mode, dict(n.properties)) for n in batch.nodes] == [
        (GraphLabel.RAW, NodeWrite.MERGE, {"estado_parseo": "error", "error_parseo": "corrupt"})
    ]
