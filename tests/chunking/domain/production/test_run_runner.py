"""RunRunner (features 043 and 045): POST /runs over the sha256s of the run, with fake ports (no data, no
docling-core)."""

import pytest

from chunking.domain import OfficialGraph, Parameters, RunRunner
from chunking.models import (
    UNPARSED,
    Chunk,
    Chunker,
    ChunkerUnavailable,
    ChunkingError,
    ChunkingParameters,
    DocumentError,
    DocumentFailure,
    GraphBatch,
    GraphLabel,
    ParsedDocument,
    RequestedChunking,
    RunOutcome,
    RunStatus,
    SinkError,
    chunked_fingerprint,
)

PARAMETERS = Parameters.resolve(RequestedChunking(), "2")
A, B, C = "a" * 64, "b" * 64, "c" * 64


def parsed(sha256: str, chunked: str | None = None, chunks: int = 0, status: str = "parseado") -> ParsedDocument:
    return ParsedDocument(sha256, status, "parse-1", "stored", chunked, chunks)


class Documents:
    """A DocumentStore over a dict; `reject` sha256s whose batch data refuses, `down` makes data not answer."""

    def __init__(self, *documents: ParsedDocument, reject: tuple[str, ...] = (), down: bool = False) -> None:
        self.documents = {d.sha256: d for d in documents}
        self.saved: list[GraphBatch] = []
        self._reject, self._down = reject, down

    def document(self, sha256: str) -> ParsedDocument | None:
        if self._down:
            raise SinkError("data is down")
        return self.documents.get(sha256)

    def save(self, batch: GraphBatch) -> None:
        if batch.nodes and batch.nodes[0].key.id in self._reject and batch.replace_from:
            raise DocumentError("data refused it")
        self.saved.append(batch)
        root = batch.nodes[0] if batch.nodes else None
        if batch.replace_from and root is not None:  # chunked: it is as the real graph would leave it
            done = self.documents[root.key.id]
            self.documents[root.key.id] = ParsedDocument(
                done.sha256,
                done.status,
                done.parse_fingerprint,
                done.content,
                str(root.properties["huella_chunking"]),
                2,
                str(root.properties["config_chunking"]),
            )


class Chunks(Chunker):
    """Two chunks per document; `fail` sha256s ("stored" + sha256 as content) can't be chunked."""

    def __init__(self, fail: str | None = None, unavailable: bool = False) -> None:
        self._fail, self._unavailable = fail, unavailable

    def available(self) -> bool:
        return True

    def version(self) -> str | None:
        return "2"

    def chunk(self, content: str, parameters: ChunkingParameters) -> list[Chunk]:
        if self._unavailable:
            raise ChunkerUnavailable("no tokenizer")
        if self._fail:
            raise ChunkingError(self._fail)
        return [Chunk(0, "uno", "T\nuno", ["T"], [1], 2), Chunk(1, "dos", "dos", [], [1], 1)]


def run(store: Documents, chunker: Chunker, *sha256s: str, simulate: bool = False) -> tuple[RunOutcome, list[str]]:
    failures: list[DocumentFailure] = []
    outcome = RunRunner.run(
        store, chunker, list(sha256s), PARAMETERS, "e1", lambda: "2026", simulate, lambda _: None, failures.append
    )
    assert [f.sha256 for f in outcome.failures] == [f.sha256 for f in failures]
    return outcome, [f.sha256 for f in failures]


def test_each_document_is_chunked_under_its_json() -> None:
    store = Documents(parsed(A), parsed(B))
    outcome, _ = run(store, Chunks(), A, B, A)
    assert outcome.chunked == [A, B] and outcome.status is RunStatus.FINISHED
    assert outcome.progress.chunks == 4
    assert [b.replace_from.id for b in store.saved if b.replace_from] == [A, B]


def test_a_document_is_never_chunked_twice_with_the_same_configuration() -> None:
    store = Documents(parsed(A), parsed(B))
    run(store, Chunks(), A, B)
    again, _ = run(store, Chunks(), B, A)  # a resume, or another run over them
    assert again.chunked == [B, A] and again.progress.skipped == 2 and again.progress.chunked == 0
    assert len(store.saved) == 2  # nothing more: not even a mark


def test_one_without_a_parse_is_sin_parseo_and_nothing_is_written() -> None:
    store = Documents(parsed(B, status="error"))
    outcome, failed = run(store, Chunks(), A, B)
    assert failed == [A, B] and store.saved == []
    assert outcome.progress.unparsed == 2


def test_one_chunked_before_feature_045_is_skipped_and_marked_for_data() -> None:
    done = chunked_fingerprint(PARAMETERS, "parse-1")
    store = Documents(parsed(A, chunked=done, chunks=2))
    outcome, _ = run(store, Chunks(), A)
    [mark] = store.saved
    assert outcome.progress.skipped == 1 and mark.replace_from is None
    assert dict(mark.nodes[0].properties) == {"config_chunking": PARAMETERS.fingerprint, "parseo_chunkeado": "parse-1"}
    assert run(Documents(parsed(A, chunked=done, chunks=2)), Chunks(), A, simulate=True)[0].progress.skipped == 1


def test_one_chunked_with_the_same_parameters_over_the_same_parse_is_skipped() -> None:
    done = chunked_fingerprint(PARAMETERS, "parse-1")
    store = Documents(parsed(A, chunked=done, chunks=2), parsed(B, chunked="other", chunks=2))
    outcome, _ = run(store, Chunks(), A, B)
    assert outcome.chunked == [A, B] and outcome.progress.skipped == 1  # A is chunked with it: it goes on


def test_simulate_counts_and_writes_nothing() -> None:
    store = Documents(parsed(A), parsed(B))
    outcome, _ = run(store, Chunks(), A, B, C, simulate=True)
    assert store.saved == []
    assert (outcome.progress.pending, outcome.progress.unparsed) == (2, 1)


def test_a_document_that_fails_keeps_the_chunks_it_had() -> None:
    store = Documents(parsed(A, chunks=5))
    outcome, failed = run(store, Chunks(fail="bad table"), A)
    assert failed == [A] and outcome.error is None and outcome.status is RunStatus.PARTIAL
    [note] = store.saved
    assert note.replace_from is None and dict(note.nodes[0].properties) == {"error_chunking": "bad table"}


def test_a_document_that_fails_without_chunks_is_marked_as_error() -> None:
    store = Documents(parsed(A))
    run(store, Chunks(fail="bad"), A)
    assert dict(store.saved[0].nodes[0].properties) == {"error_chunking": "bad", "estado_chunking": "error"}


def test_a_batch_data_refuses_only_fails_its_document() -> None:
    store = Documents(parsed(A), parsed(B), reject=(A,))
    outcome, failed = run(store, Chunks(), A, B)
    assert failed == [A] and outcome.chunked == [B]


@pytest.mark.parametrize(
    ("store", "chunker"), [(Documents(down=True), Chunks()), (Documents(parsed(A)), Chunks(unavailable=True))]
)
def test_data_down_or_no_chunker_stops_it(store: Documents, chunker: Chunker) -> None:
    outcome, _ = run(store, chunker, A, B)
    assert outcome.error and outcome.chunked == [] and outcome.status is RunStatus.FAILED


def test_what_it_writes_says_how_and_from_which_experiment() -> None:
    chunks = Chunks().chunk("", PARAMETERS)
    batch = OfficialGraph.chunked(A, chunks, PARAMETERS, "parse-1", "2026", "e1")
    root = batch.nodes[0]
    assert root.key.label is GraphLabel.JSON and root.mode.value == "merge"
    assert root.properties["huella_chunking"] == chunked_fingerprint(PARAMETERS, "parse-1")
    assert (root.properties["config_chunking"], root.properties["parseo_chunkeado"]) == (
        PARAMETERS.fingerprint,
        "parse-1",
    )
    assert (root.properties["experimento_config"], root.properties["max_tokens"]) == ("e1", 126)
    labels = [n.key.label for n in batch.nodes]
    assert labels.count(GraphLabel.SECCION) == 2 and labels.count(GraphLabel.FRAGMENTOS) == 2
    assert {n.key.id for n in batch.nodes if n.key.label is GraphLabel.FRAGMENTOS} == {f"{A}:0", f"{A}:1"}


def test_unparsed_is_said_with_the_way_out() -> None:
    assert "POST /parsing/runs" in UNPARSED


def test_unparsed_ones_dont_make_it_partial() -> None:
    outcome, _ = run(Documents(parsed(A)), Chunks(), A, B)
    assert outcome.progress.unparsed == 1 and outcome.status is RunStatus.FINISHED


def test_stop_ends_the_run_interrupted_before_the_next_document() -> None:
    store = Documents(parsed(A), parsed(B))
    outcome = RunRunner.run(store, Chunks(), [A, B], PARAMETERS, None, lambda: "2026", stop=lambda: bool(store.saved))
    assert outcome.stopped and outcome.chunked == [A] and outcome.status is RunStatus.INTERRUPTED
    assert [b.replace_from.id for b in store.saved if b.replace_from] == [A]  # what it did stays
