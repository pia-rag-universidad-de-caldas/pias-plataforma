"""ParsingRunner: a run over the sha256 it is given (feature 042). It never chooses what to parse: whoever asks does.

For each sha256, in order and once: no RAW → missing; already parsed with this fingerprint (and no `redo`) → skipped;
otherwise the RAW is read from data, parsed (a partial one of this fingerprint resumes from its pending pages) and
written in one batch. A document's failure (its fault, or data refusing its batch) is noted on its RAW and the run goes
on; data down or Docling unable to load stops the run, writing nothing more.
"""

from collections.abc import Callable
from contextlib import suppress
from dataclasses import replace

from parsing.models import (
    DocumentError,
    DocumentResult,
    DocumentState,
    ParsedSink,
    ParseError,
    Parser,
    ParserUnavailable,
    ParseStatus,
    ParsingRequest,
    RawSource,
    RunOutcome,
    RunProgress,
    SinkError,
    StoredParse,
)

from .check import Check
from .graph import ParsedGraph

type OnDocument = Callable[[DocumentResult, RunProgress], None]

_COUNTERS = {
    DocumentState.PARSED: "parsed",
    DocumentState.PARTIAL: "partial",
    DocumentState.ERROR: "errors",
    DocumentState.SKIPPED: "skipped",
    DocumentState.MISSING: "missing",
}


def _counted(progress: RunProgress, result: DocumentResult) -> RunProgress:
    counter = _COUNTERS.get(result.state)
    changed = {counter: getattr(progress, counter) + 1} if counter else {}
    return replace(progress, done=progress.done + 1, resumed=progress.resumed + int(result.resumed), **changed)


class ParsingRunner:
    @staticmethod
    def resumable(previous: StoredParse | None, fingerprint: str, redo: bool) -> StoredParse | None:
        """A partial parsing of this fingerprint goes on from its pending pages; anything else starts over."""
        if previous is None or redo or previous.status is not ParseStatus.PARTIAL:
            return None
        return previous if previous.fingerprint == fingerprint and previous.coverage.pending else None

    @staticmethod
    def run(
        request: ParsingRequest,
        source: RawSource,
        sink: ParsedSink,
        parser: Parser,
        fingerprint: str,
        now: Callable[[], str],
        timer: Callable[[], float],
        on_document: OnDocument = lambda result, progress: None,
    ) -> RunOutcome:
        sha256s = Check.unique(request.sha256s)
        progress = RunProgress(total=len(sha256s))
        docling = parser.version() or ""
        try:
            states = source.states(sha256s)
            for sha256 in sha256s:
                state = states.get(sha256)
                if state is None:
                    result = DocumentResult(sha256, DocumentState.MISSING, error="data has no RAW with this sha256")
                elif not request.redo and Check.done(state, fingerprint):
                    result = DocumentResult(sha256, DocumentState.SKIPPED)
                elif request.simulate:
                    resumed = state.status is ParseStatus.PARTIAL and state.fingerprint == fingerprint
                    result = DocumentResult(sha256, DocumentState.SIMULATED, resumed=resumed and not request.redo)
                else:
                    result = ParsingRunner._one(
                        sha256, request.redo, source, sink, parser, fingerprint, docling, now, timer
                    )
                progress = _counted(progress, result)
                on_document(result, progress)
        except (SinkError, ParserUnavailable) as e:
            return RunOutcome(progress, str(e) or type(e).__name__)
        return RunOutcome(progress)

    @staticmethod
    def _one(
        sha256: str,
        redo: bool,
        source: RawSource,
        sink: ParsedSink,
        parser: Parser,
        fingerprint: str,
        docling: str,
        now: Callable[[], str],
        timer: Callable[[], float],
    ) -> DocumentResult:
        raw = source.get(sha256)
        if raw is None:
            return DocumentResult(sha256, DocumentState.MISSING, error="data has no RAW with this sha256")
        previous = ParsingRunner.resumable(sink.previous(sha256), fingerprint, redo)
        started = timer()
        try:
            output = parser.parse(raw.name, raw.content, previous)
        except ParseError as e:
            return ParsingRunner._failed(sink, sha256, str(e))
        batch = ParsedGraph.parsed(raw, output, fingerprint, docling, now(), timer() - started)
        try:
            sink.save(batch)
        except DocumentError as e:
            return ParsingRunner._failed(sink, sha256, f"data refused its JSON: {e}")
        state = DocumentState.PARSED if ParsedGraph.status(output) is ParseStatus.PARSED else DocumentState.PARTIAL
        return DocumentResult(sha256, state, resumed=previous is not None, ocr_pages=output.ocr_pages)

    @staticmethod
    def _failed(sink: ParsedSink, sha256: str, error: str) -> DocumentResult:
        with suppress(DocumentError):  # if its failure can't be noted, the run still reports it
            sink.save(ParsedGraph.failed(sha256, error))
        return DocumentResult(sha256, DocumentState.ERROR, error=error)
