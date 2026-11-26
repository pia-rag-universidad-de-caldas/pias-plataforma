"""ExperimentRunner: one chunking experiment (features 043, 045 and 059). Takes the sha256s it is given (or those of
another experiment, or every parsed JSON data has when its turn comes), chunks each parsed document with the
experiment's parameters and records everything in the graph, apart from the official chunks, document by document.
A problem with one document is recorded and the experiment goes on; only data failing (or the chunker, for every
document) stops it. A resume chunks only the documents it didn't get to chunk, with its own parameters, and counts the
results over all of them."""

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from chunking.domain.progress import advanced
from chunking.domain.stats import token_stats
from chunking.models import (
    UNPARSED,
    Chunk,
    Chunker,
    ChunkerUnavailable,
    ChunkingError,
    DocumentError,
    DocumentFailure,
    DocumentResult,
    DocumentStore,
    DocumentUse,
    ExperimentOutcome,
    ExperimentProgress,
    ExperimentRequest,
    ExperimentResults,
    ExperimentStore,
    SinkError,
)

from .graph import ExperimentGraph

type ProgressCallback = Callable[[ExperimentProgress], None]


@dataclass(frozen=True)
class Resolution:
    """The documents an experiment takes (parsed, in order, each once) and those it can't (sin_parseo)."""

    sha256s: list[str]
    unparsed: list[str]


@dataclass(frozen=True)
class Addition:
    """Documents asked to enter an experiment (feature 062), told apart."""

    added: list[str]  # parsed and new: they enter its list
    already: list[str]  # it had them
    unparsed: list[str]  # new but without a parse: they don't enter


def _ignore(_: object) -> None:
    pass


class ExperimentRunner:
    @staticmethod
    def resolve(store: ExperimentStore, request: ExperimentRequest) -> Resolution:
        """With `all` (feature 059), every parsed JSON, without reading each one: they are parsed (one that no
        longer is when its turn comes is sin_parseo then). Otherwise each asked document is read to tell."""
        if request.all:
            return Resolution(list(dict.fromkeys(store.parsed_documents())), [])
        asked = request.sha256s or (store.documents(request.from_experiment) if request.from_experiment else [])
        parsed: list[str] = []
        unparsed: list[str] = []
        for sha256 in dict.fromkeys(asked):
            document = store.document(sha256)
            (parsed if document is not None and document.parsed else unparsed).append(sha256)
        return Resolution(parsed, unparsed)

    @staticmethod
    def listed(store: ExperimentStore, request: ExperimentRequest, id: str) -> list[str]:
        """An experiment's frozen list: its sha256s, those of the experiment it came from or, of one of every parsed
        JSON (feature 059), those it got to (its EXP_DOCUMENTO)."""
        if request.all:
            return store.documents(id)
        asked = request.sha256s or (store.documents(request.from_experiment) if request.from_experiment else [])
        return list(dict.fromkeys(asked))

    @staticmethod
    def addition(store: ExperimentStore, listed: Sequence[str], asked: Sequence[str]) -> Addition:
        """What adding `asked` to a frozen list does (feature 062): the new parsed ones enter, in the order asked; one
        it has is `already`; a new one without a parse is `unparsed` and doesn't enter."""
        have = set(listed)
        added: list[str] = []
        already: list[str] = []
        unparsed: list[str] = []
        for sha256 in dict.fromkeys(asked):
            if sha256 in have:
                already.append(sha256)
                continue
            document = store.document(sha256)
            (added if document is not None and document.parsed else unparsed).append(sha256)
        return Addition(added, already, unparsed)

    @staticmethod
    def pending(
        store: ExperimentStore, request: ExperimentRequest, uses: Sequence[DocumentUse]
    ) -> tuple[Resolution, list[DocumentUse]]:
        """For a resume: what is still to chunk (parsed now, without a chunked EXP_USA) and what it keeps."""
        chunked = {u.sha256: u for u in uses if u.chunked}
        full = ExperimentRunner.resolve(store, request)
        pending = [sha256 for sha256 in full.sha256s if sha256 not in chunked]
        return Resolution(pending, [s for s in full.unparsed if s not in chunked]), list(chunked.values())

    @staticmethod
    def run(
        store: DocumentStore,
        chunker: Chunker,
        id: str,
        request: ExperimentRequest,
        resolution: Resolution,
        on_progress: ProgressCallback = _ignore,
        kept: Sequence[DocumentUse] = (),
    ) -> ExperimentOutcome:
        """`kept`: on a resume, the documents already chunked; they count in the results as they are."""
        progress = ExperimentProgress(
            files=len(resolution.sha256s) + len(kept), done=len(kept), chunks=sum(u.chunks for u in kept)
        )
        failures = [DocumentFailure(sha256, UNPARSED) for sha256 in resolution.unparsed]
        done = [DocumentResult(u.sha256, u.chunks, sum(u.tokens)) for u in kept]
        tokens: list[int] = [t for u in kept for t in u.tokens]
        on_progress(progress)  # the real total: with `all` it is only known now
        started = time.monotonic()
        error: str | None = None
        try:
            for sha256 in resolution.sha256s:
                begun = time.monotonic()
                document = store.document(sha256)
                chunks: list[Chunk] = []
                problem: str | None = None
                if document is None or not document.parsed or document.content is None:
                    problem = UNPARSED  # it was parsed when the experiment was asked for
                else:
                    try:
                        chunks = chunker.chunk(document.content, request.parameters)
                    except ChunkingError as failed:
                        problem = str(failed)
                try:
                    store.save(ExperimentGraph.document(id, sha256, chunks, problem, time.monotonic() - begun))
                except DocumentError as rejected:
                    problem, chunks = str(rejected), []
                if problem:
                    failures.append(DocumentFailure(sha256, problem))
                    progress = advanced(progress, done=1, errors=1)
                else:
                    done.append(DocumentResult(sha256, len(chunks), sum(c.tokens for c in chunks)))
                    tokens += [c.tokens for c in chunks]
                    progress = advanced(progress, done=1, chunks=len(chunks))
                on_progress(progress)
        except (SinkError, ChunkerUnavailable) as stopped:
            error = str(stopped)
        results = ExperimentResults(
            documents=len(resolution.sha256s) + len(kept) + len(resolution.unparsed),
            chunked=len(done),
            errors=progress.errors,
            unparsed=len(resolution.unparsed),
            chunks=progress.chunks,
            tokens=token_stats(tokens),
            seconds=round(time.monotonic() - started, 3),
            by_document=done,
            failures=failures,
        )
        return ExperimentOutcome(results, progress, error)
