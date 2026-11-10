"""RunRunner: POST /chunking/runs (features 043 and 045). Goes over the sha256s of a run with the configuration it was
asked with and replaces what hung from each JSON. A document is never chunked twice with the same configuration over
the same parse: each is looked at right before chunking it, and one already done is skipped (and counted as chunked:
it is). A document without a parse is `sin_parseo`; one that fails is recorded and the rest goes on. Only data failing
(or the chunker, for every document) stops it. A resume goes over the same list again: what is done is skipped."""

from collections.abc import Callable
from contextlib import suppress

from chunking.domain.progress import advanced
from chunking.models import (
    UNPARSED,
    Chunker,
    ChunkerUnavailable,
    ChunkingError,
    ChunkingParameters,
    DocumentError,
    DocumentFailure,
    DocumentStore,
    RunOutcome,
    RunProgress,
    SinkError,
    chunked_fingerprint,
)

from .graph import OfficialGraph

type ProgressCallback = Callable[[RunProgress], None]
type FailureCallback = Callable[[DocumentFailure], None]


def _ignore(_: object) -> None:
    pass


class RunRunner:
    @staticmethod
    def run(
        store: DocumentStore,
        chunker: Chunker,
        sha256s: list[str],
        parameters: ChunkingParameters,
        experiment: str | None,
        clock: Callable[[], str],
        simulate: bool = False,
        on_progress: ProgressCallback = _ignore,
        on_failure: FailureCallback = _ignore,
    ) -> RunOutcome:
        progress = RunProgress()
        chunked: list[str] = []
        failures: list[DocumentFailure] = []

        def fail(sha256: str, error: str, counter: str) -> None:
            nonlocal progress
            progress = advanced(progress, **{counter: 1})
            failure = DocumentFailure(sha256, error)
            failures.append(failure)
            on_failure(failure)

        try:
            for sha256 in dict.fromkeys(sha256s):
                document = store.document(sha256)
                if document is None or not document.parsed or document.content is None:
                    fail(sha256, UNPARSED, "unparsed")
                elif document.chunked == chunked_fingerprint(parameters, document.parse_fingerprint):
                    progress = advanced(progress, skipped=1)
                    chunked.append(sha256)
                    if not simulate and document.configuration != parameters.fingerprint:
                        with suppress(DocumentError):  # only so that data stops counting it as missing
                            store.save(OfficialGraph.marked(sha256, parameters, document.parse_fingerprint))
                elif simulate:
                    progress = advanced(progress, pending=1)
                else:
                    progress = advanced(progress, pending=1)
                    try:
                        chunks = chunker.chunk(document.content, parameters)
                        batch = OfficialGraph.chunked(
                            sha256, chunks, parameters, document.parse_fingerprint, clock(), experiment
                        )
                        store.save(batch)
                    except (ChunkingError, DocumentError) as error:
                        fail(sha256, str(error), "errors")
                        with suppress(DocumentError):  # the failure is already in the record of the run
                            store.save(OfficialGraph.failed(sha256, str(error), document.chunks > 0))
                    else:
                        progress = advanced(progress, chunked=1, chunks=len(chunks))
                        chunked.append(sha256)
                on_progress(progress)
        except (SinkError, ChunkerUnavailable) as error:
            return RunOutcome(progress, chunked, failures, str(error))
        return RunOutcome(progress, chunked, failures)
