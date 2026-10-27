"""Runner (feature 023): a production run over fake ports. One bad document never stops it; only the source or the
sink failing does."""

from collections.abc import Iterator

from chunking.domain import Runner
from chunking.models import (
    Chunk,
    ChunkedDocument,
    ChunkingParameters,
    ConversionError,
    ConversionParameters,
    ConvertedDocument,
    Converter,
    DocumentError,
    DocumentFailure,
    DocumentFilter,
    DocumentStatus,
    GraphBatch,
    GraphLabel,
    ProcessedDocument,
    RunOutcome,
    RunRequest,
    SinkError,
    SourceDocument,
    TableMode,
)

PARAMETERS = ChunkingParameters("tok", 512, True, False, True, TableMode.ACCURATE, "2")


def doc(n: int, sha: str | None = None) -> SourceDocument:
    return SourceDocument(f"2024/{n}.pdf", f"v/{n}.pdf", f"{n}.pdf", sha or f"h{n}", "pdf", 2024, "020055")


class Source:
    def __init__(self, *pages: list[SourceDocument]) -> None:
        self._pages = pages

    def pages(
        self, filter: DocumentFilter, per_page: int, first: int = 1, last: int | None = None
    ) -> Iterator[list[SourceDocument]]:
        yield from self._pages

    def find(self, sha256: str) -> SourceDocument:
        for page in self._pages:
            for document in page:
                if document.sha256 == sha256:
                    return document
        raise DocumentError(f"no file with {sha256}")

    def content(self, document: SourceDocument) -> bytes:
        return document.name.encode()


class Sink:
    def __init__(self, processed: dict[str, ProcessedDocument] | None = None, broken: bool = False) -> None:
        self._processed = processed or {}
        self.saved: list[GraphBatch] = []
        self.discarded: list[str] = []
        self.broken = broken

    def save(self, batch: GraphBatch) -> int:
        if self.broken:
            raise SinkError("data is down")
        self.saved.append(batch)
        return len(batch.nodes)

    def processed(self) -> dict[str, ProcessedDocument]:
        return self._processed

    def discard(self, sha256: str) -> None:
        self.discarded.append(sha256)

    def states(self) -> dict[str, object]:
        return {
            str(n.properties["origen"]): n.properties["estado"]
            for b in self.saved
            for n in b.nodes
            if n.key.label == GraphLabel.JSON
        }


class Docling(Converter):
    """`bad.pdf` can't be converted; `blank.pdf` has no text."""

    def available(self) -> bool:
        return True

    def version(self) -> str | None:
        return "2"

    def chunk(self, name: str, content: bytes, parameters: ChunkingParameters) -> ChunkedDocument:
        if name == "bad.pdf":
            raise ConversionError("broken PDF")
        if name == "blank.pdf":
            return ChunkedDocument([])
        return ChunkedDocument([Chunk(0, "t", "h t", ["h"], [1], 3), Chunk(1, "u", "h u", ["h"], [1], 3)])

    def convert(self, name: str, content: bytes, parameters: ConversionParameters) -> ConvertedDocument:
        raise AssertionError("production runs only chunk")


def run(source: Source, sink: Sink, request: RunRequest) -> tuple[RunOutcome, list[DocumentFailure]]:
    failures: list[DocumentFailure] = []
    outcome = Runner.run(source, sink, Docling(), request, PARAMETERS, 10, lambda _: None, failures.append)
    return outcome, failures


def done(document: SourceDocument, fingerprint: str = PARAMETERS.fingerprint) -> ProcessedDocument:
    return ProcessedDocument(document.origin, document.sha256 or "", fingerprint, DocumentStatus.CHUNKED)


def test_pages_skip_what_is_done_and_limit_counts_the_processed() -> None:
    first, second = [doc(1), doc(2)], [doc(3), doc(4)]
    sink = Sink({doc(1).origin: done(doc(1))})
    outcome, _ = run(Source(first, second), sink, RunRequest(limit=2))
    assert (outcome.progress.skipped, outcome.progress.pending, outcome.progress.chunked) == (1, 2, 2)
    assert outcome.progress.chunks == 4 and sorted(sink.states()) == ["2024/2.pdf", "2024/3.pdf"]


def test_simulate_counts_and_writes_nothing() -> None:
    sink = Sink()
    outcome, _ = run(Source([doc(1), doc(2)]), sink, RunRequest(simulate=True))
    assert outcome.progress.pending == 2 and outcome.progress.chunked == 0 and sink.saved == []


def test_a_bad_document_is_stored_as_failed_and_the_run_goes_on() -> None:
    bad = SourceDocument("2024/bad.pdf", "v/bad.pdf", "bad.pdf", "hb", "pdf", 2024, None)
    blank = SourceDocument("2024/blank.pdf", "v/blank.pdf", "blank.pdf", "hx", "pdf", 2024, None)
    sink = Sink()
    outcome, failures = run(Source([bad, blank, doc(1)]), sink, RunRequest())
    assert sink.states() == {"2024/bad.pdf": "error", "2024/blank.pdf": "error", "2024/1.pdf": "fragmentado"}
    assert [f.error for f in failures] == ["broken PDF", "Docling extracted no text (a scanned document? OCR is off)"]
    assert (outcome.progress.errors, outcome.progress.chunked, outcome.error) == (2, 1, None)


def test_an_origin_with_another_content_discards_the_old_document() -> None:
    sink = Sink({doc(1).origin: done(doc(1, sha="old"))})
    run(Source([doc(1)]), sink, RunRequest())
    assert sink.discarded == ["old"]


def test_sha256s_are_exactly_those_once_even_if_done_and_an_unknown_one_fails_alone() -> None:
    sink = Sink({doc(1).origin: done(doc(1))})
    outcome, failures = run(Source([doc(1), doc(2)]), sink, RunRequest(sha256s=["h1", "h1", "nope", "h2"]))
    assert sorted(sink.states()) == ["2024/1.pdf", "2024/2.pdf"]
    assert [(f.sha256, f.origin) for f in failures] == [("nope", None)]
    assert outcome.progress.chunked == 2


def test_the_sink_failing_stops_the_run() -> None:
    outcome, _ = run(Source([doc(1), doc(2)]), Sink(broken=True), RunRequest())
    assert outcome.error == "data is down" and outcome.progress.chunked == 0
