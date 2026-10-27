"""Runner: one chunking run, from the source to the sink, one page (or one origin) at a time.

A problem with one document (ingesta doesn't have it, Docling can't convert it, data rejects it) is recorded, stored
in the graph as an error when possible, and the run goes on. Only the source or the sink failing stops the run.
"""

from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import datetime

from chunking.models import (
    ChunkingParameters,
    ChunkSink,
    ChunkSource,
    ConversionError,
    Converter,
    DocumentError,
    DocumentFailure,
    ProcessedDocument,
    RunOutcome,
    RunProgress,
    RunRequest,
    SinkError,
    SourceDocument,
    SourceError,
)

from .hierarchy import Hierarchy
from .selection import Selection

type ProgressCallback = Callable[[RunProgress], None]
type FailureCallback = Callable[[DocumentFailure], None]

NO_TEXT = "Docling extracted no text (a scanned document? OCR is off)"
NO_SHA256 = "ingesta has no sha256 for it"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class _Run:
    """The state of one run (its counters and what was already in the sink)."""

    def __init__(
        self,
        source: ChunkSource,
        sink: ChunkSink,
        converter: Converter,
        request: RunRequest,
        parameters: ChunkingParameters,
        on_progress: ProgressCallback,
        on_failure: FailureCallback,
    ) -> None:
        self.source = source
        self.sink = sink
        self.converter = converter
        self.request = request
        self.parameters = parameters
        self.on_progress = on_progress
        self.on_failure = on_failure
        self.progress = RunProgress()
        self.processed: dict[str, ProcessedDocument] = {}

    def count(self, **changes: int) -> None:
        self.progress = replace(
            self.progress, **{name: getattr(self.progress, name) + value for name, value in changes.items()}
        )
        self.on_progress(self.progress)

    def fail(self, error: str, origin: str | None, sha256: str | None) -> None:
        self.on_failure(DocumentFailure(error, origin, sha256))
        self.count(errors=1)

    def execute(self, per_page: int) -> None:
        self.processed = self.sink.processed()
        explicit = bool(self.request.sha256s)
        for page in self.batches(per_page):
            selected = (
                page
                if explicit
                else Selection.pending(page, self.processed, self.parameters.fingerprint, self.request.retry_errors)
            )
            if len(page) > len(selected):
                self.count(skipped=len(page) - len(selected))
            for document in selected:
                if self.request.limit is not None and self.progress.pending >= self.request.limit:
                    return
                self.count(pending=1)
                if not self.request.simulate:
                    self.process(document)

    def batches(self, per_page: int) -> Iterator[list[SourceDocument]]:
        """The source's pages, or one batch per requested sha256 (repeated ones once; a missing one fails alone)."""
        if not self.request.sha256s:
            yield from self.source.pages(self.request.filter, per_page)
            return
        for sha256 in dict.fromkeys(self.request.sha256s):
            try:
                document = self.source.find(sha256)
            except DocumentError as error:
                self.fail(str(error), None, sha256)
                continue
            yield [document]

    def process(self, document: SourceDocument) -> None:
        if not document.sha256:
            self.fail(NO_SHA256, document.origin, None)  # without sha256 it has no id in the graph: only reported
            return
        try:
            content = self.source.content(document)
            chunked = self.converter.chunk(document.name, content, self.parameters)
            if not chunked.chunks:
                raise ConversionError(NO_TEXT)
            self.sink.save(Hierarchy.build(document, chunked, self.parameters, _now()))
        except (DocumentError, ConversionError) as error:
            self.store_failure(document, str(error) or type(error).__name__)
        else:
            self.count(chunked=1, chunks=len(chunked.chunks))
        self.discard_previous(document)

    def store_failure(self, document: SourceDocument, error: str) -> None:
        self.fail(error, document.origin, document.sha256)
        try:
            self.sink.save(Hierarchy.failed(document, error, self.parameters, _now()))
        except DocumentError as rejected:
            self.on_failure(
                DocumentFailure(f"could not be stored as failed: {rejected}", document.origin, document.sha256)
            )

    def discard_previous(self, document: SourceDocument) -> None:
        """The origin was stored with another content: that document is replaced by this one."""
        previous = self.processed.get(document.origin)
        if previous is not None and previous.sha256 != document.sha256:
            self.sink.discard(previous.sha256)


class Runner:
    @staticmethod
    def run(
        source: ChunkSource,
        sink: ChunkSink,
        converter: Converter,
        request: RunRequest,
        parameters: ChunkingParameters,
        per_page: int,
        on_progress: ProgressCallback,
        on_failure: FailureCallback,
    ) -> RunOutcome:
        """Chunks what `request` asks for. With `sha256s`, exactly those documents (even if already chunked); otherwise
        the source's pages, one at a time, keeping only the pending documents of each. `limit` counts the
        documents processed across pages; `simulate` only counts them."""
        run = _Run(source, sink, converter, request, parameters, on_progress, on_failure)
        try:
            run.execute(per_page)
        except (SourceError, SinkError) as error:
            return RunOutcome(run.progress, str(error))
        return RunOutcome(run.progress)
