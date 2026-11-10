"""What chunking writes in the graph is what its mappers read back (features 043 and 045), and what parsing left is read
as a ParsedDocument."""

from dataclasses import asdict

from chunking.adapters.data import mappers as to
from chunking.adapters.http import Json
from chunking.domain import ExperimentGraph, OfficialGraph, Parameters, RunGraph
from chunking.models import (
    Chunk,
    ChunkingRun,
    DocumentFailure,
    DocumentResult,
    ExperimentProgress,
    ExperimentRequest,
    ExperimentResults,
    ExperimentStatus,
    JsonChunkingProperties,
    RequestedChunking,
    RunProgress,
    RunStatus,
    TokenStats,
    chunked_fingerprint,
)

A = "a" * 64
PARAMETERS = Parameters.resolve(RequestedChunking(max_tokens=64), "2.106.0")
CHUNKS = [Chunk(0, "uno", "T\nuno", ["T"], [1], 2)]


def as_read(properties: object) -> dict[str, Json]:
    """Properties as data answers them (JSON)."""
    assert isinstance(properties, dict)
    return dict(properties)


def test_a_parsed_json_is_read_with_what_chunking_added() -> None:
    chunked = OfficialGraph.chunked(A, CHUNKS, PARAMETERS, "parse-1", "2026", None).nodes[0].properties
    raw = {"sha256": A, "estado": "parseado", "fingerprint_parseo": "parse-1", "documento": "x", **as_read(chunked)}
    document = to.parsed(A, raw)
    assert document.parsed and document.content == "x"
    assert (document.chunked, document.chunks) == (chunked_fingerprint(PARAMETERS, "parse-1"), 1)
    assert to.official_parameters(raw) == PARAMETERS


def test_a_json_without_a_document_is_not_parsed() -> None:
    document = to.parsed(A, {"estado": "parseado"})
    assert not document.parsed and document.chunked is None and document.sha256 == A


def test_a_json_chunking_failed_on_has_no_official_parameters() -> None:
    raw: dict[str, Json] = {"estado_chunking": "error", "error_chunking": "bad"}
    assert to.official_parameters(raw) is None and to.parsed(A, raw).chunked is None


def test_stored_reads_a_missing_key_as_none() -> None:
    p = to.stored({"fragmentos": 3}, JsonChunkingProperties)
    read: list[object] = [p["fragmentos"], p["tokenizador"]]
    assert read == [3, None]


def test_an_experiment_goes_and_comes_back() -> None:
    request = ExperimentRequest("prueba", "d", PARAMETERS, [A])
    results = ExperimentResults(1, 1, 0, 0, 1, TokenStats(2, 2.0, 2, 2), 0.5, [DocumentResult(A, 1, 2)], [])
    progress = ExperimentProgress(files=1, done=1, chunks=1)
    raw = {
        **as_read(ExperimentGraph.experiment("e1", request, 1, "2026-01-01").nodes[0].properties),
        **as_read(ExperimentGraph.finish("e1", results, progress, None, "2026-01-02").nodes[0].properties),
    }
    record = to.record("e1", raw)
    assert (record.name, record.status, record.finished) == ("prueba", ExperimentStatus.FINISHED, "2026-01-02")
    assert (record.results, record.progress, record.parameters) == (results, progress, PARAMETERS)


def test_a_run_goes_and_comes_back() -> None:
    run = ChunkingRun(
        "r1",
        RunStatus.PARTIAL,
        "2026",
        False,
        PARAMETERS,
        [A, "b" * 64],
        True,
        2,
        20,
        "e1",
        "2026",
        "2027",
        RunProgress(pending=2, chunked=1, chunks=3, errors=1),
        [DocumentFailure("b" * 64, "bad")],
        [A],
        None,
        1,
    )
    stored = as_read(RunGraph.record(run).nodes[0].properties)
    assert to.run("r1", stored) == run


def test_a_run_stored_as_running_was_interrupted_and_one_of_before_is_none() -> None:
    run = ChunkingRun("r1", RunStatus.RUNNING, "2026", False, PARAMETERS, [], frozen=False)
    read = to.run("r1", as_read(RunGraph.record(run).nodes[0].properties))
    assert read is not None and read.status is RunStatus.INTERRUPTED and not read.frozen
    assert to.run("old", {"estado": "finished", "pedido_en": "2026"}) is None


def test_an_experiment_use_is_read_with_the_tokens_of_its_chunks() -> None:
    [use] = ExperimentGraph.document("e1", A, CHUNKS, None, 0.5).links[:1]
    read = to.use(A, as_read(use.properties))
    assert (read.chunked, read.chunks, read.tokens) == (True, 1, [2])
    assert to.use(A, {"estado": "error"}).tokens == []


def test_a_configuration_that_cant_be_read_is_none() -> None:
    assert to.config({"chunker": "otro", "origen": "manual"}) is None
    read = to.config({"chunker": "page", "origen": "manual", "modificado_en": "2026"})
    assert read is not None and asdict(read.requested)["chunker"] == "page"
