"""ExperimentRunner: one chunking experiment (feature 025). Resolves its files, converts each one (or reuses the
conversion stored with the same fingerprint), assigns a strategy to each section by the plan, cuts the sections and
records everything in the graph, document by document. A problem with one document is recorded and the experiment
goes on; only ingesta or data failing stops it."""

import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime

from chunking.config import GRAPH_PAGE_SIZE
from chunking.domain.progress import advanced
from chunking.models import (
    ChunkPiece,
    ConversionError,
    ConvertedDocument,
    Converter,
    DocumentError,
    DocumentFailure,
    ExperimentFile,
    ExperimentOutcome,
    ExperimentProgress,
    ExperimentRequest,
    ExperimentResults,
    FileResolution,
    FileSelection,
    GroupResult,
    JsonSelection,
    OfficialDocument,
    Plan,
    RecordingStore,
    SectionAssignment,
    SectionChunker,
    SelectionStore,
    SinkError,
    SourceDocument,
    SourceError,
    rule_name,
)
from chunking.models import ChunkSource as Source

from .graph import ExperimentGraph
from .plan import Planner
from .scoring import token_stats

type ProgressCallback = Callable[[ExperimentProgress], None]


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class _Group:
    """What a strategy (or a rule) accumulates during an experiment."""

    sections: int = 0
    tokens: list[int] = field(default_factory=list)
    seconds: float = 0.0

    def result(self) -> GroupResult:
        return GroupResult(self.sections, len(self.tokens), token_stats(self.tokens), round(self.seconds, 3))


type _Selector = Callable[[Source, SelectionStore, FileSelection, int, list[DocumentFailure]], list[SourceDocument]]


def _by_sha256s(
    source: Source, store: SelectionStore, files: FileSelection, per_page: int, failures: list[DocumentFailure]
) -> list[SourceDocument]:
    """Exactly those (repeated ones once); one ingesta doesn't have fails alone."""
    documents = []
    for sha256 in dict.fromkeys(files.sha256s):
        try:
            documents.append(source.find(sha256))
        except DocumentError as error:
            failures.append(DocumentFailure(str(error), None, sha256))
    return documents


def _from_experiment(
    source: Source, store: SelectionStore, files: FileSelection, per_page: int, failures: list[DocumentFailure]
) -> list[SourceDocument]:
    """The documents of an earlier experiment, as ingesta described them then."""
    documents = []
    for used in store.documents(files.from_experiment or ""):
        document = store.source(used.conversion_id)
        if document is None:
            failures.append(DocumentFailure("its conversion is no longer in the graph", used.origin, used.sha256))
        else:
            documents.append(document)
    return documents


def _page_range(
    source: Source, store: SelectionStore, files: FileSelection, per_page: int, failures: list[DocumentFailure]
) -> list[SourceDocument]:
    """Ingesta's pages `first` to `last` of the filter (feature 028)."""
    assert files.filter is not None and files.pages is not None  # see _SELECTORS
    pages = source.pages(files.filter, files.per_page or per_page, files.pages.first, files.pages.last)
    return [document for page in pages for document in page]


def _filtered(
    source: Source, store: SelectionStore, files: FileSelection, per_page: int, failures: list[DocumentFailure]
) -> list[SourceDocument]:
    """The filter's documents, page by page, up to `limit` (no more pages are asked for once it is reached)."""
    assert files.filter is not None  # see _SELECTORS
    documents: list[SourceDocument] = []
    for page in source.pages(files.filter, files.per_page or per_page):
        if files.limit is None:
            documents += page
            continue
        documents += page[: files.limit - len(documents)]
        if len(documents) >= files.limit:
            break
    return documents


# The first form of `files` that holds picks the selector (the API lets only one through; from_json goes apart: its
# documents are official JSON, not ingesta's). A new form is its selector and its line here.
_SELECTORS: list[tuple[Callable[[FileSelection], bool], _Selector]] = [
    (lambda files: bool(files.sha256s), _by_sha256s),
    (lambda files: bool(files.from_experiment), _from_experiment),
    (lambda files: files.filter is not None and files.pages is not None, _page_range),
    (lambda files: files.filter is not None, _filtered),
]


def _first_of_each[T](items: Iterable[T], sha256: Callable[[T], str]) -> Iterator[T]:
    """Each content once, the first time it comes, in order."""
    seen: set[str] = set()
    for item in items:
        if sha256(item) not in seen:
            seen.add(sha256(item))
            yield item


class ExperimentRunner:
    @staticmethod
    def resolve(source: Source, store: SelectionStore, request: ExperimentRequest, per_page: int) -> FileResolution:
        """The files that enter (in order, each once) and whether their conversion already exists."""
        files = request.files
        if files.from_json is not None:
            return ExperimentRunner._official(store, files.from_json)
        failures: list[DocumentFailure] = []
        selector = next((select for holds, select in _SELECTORS if holds(files)), None)
        documents = selector(source, store, files, per_page, failures) if selector else []
        with_sha256 = []
        for document in documents:
            if document.sha256:
                with_sha256.append(document)
            else:
                failures.append(DocumentFailure("ingesta has no sha256 for it", document.origin, None))
        found = []
        for document in _first_of_each(with_sha256, lambda d: d.sha256 or ""):
            conversion_id = ExperimentGraph.conversion_id(document.sha256 or "", request.conversion)
            found.append(ExperimentFile(document, store.has_conversion(conversion_id), conversion_id))
        return FileResolution(found, failures)

    @staticmethod
    def _official(store: SelectionStore, selection: JsonSelection) -> FileResolution:
        """Official JSON nodes (feature 028): their content is already converted, so nothing goes through Docling."""
        officials: list[OfficialDocument] = []
        failures: list[DocumentFailure] = []
        if selection.sha256s:
            for sha256 in dict.fromkeys(selection.sha256s):
                official = store.official(sha256)
                if official is None:
                    failures.append(DocumentFailure("there is no official JSON with that sha256", None, sha256))
                else:
                    officials.append(official)
        else:
            pages = selection.pages
            first, last = (pages.first, pages.last) if pages else (1, None)
            for page in store.official_pages(selection.per_page or GRAPH_PAGE_SIZE, first, last):
                officials += page
        found: list[ExperimentFile] = []
        for official in _first_of_each(officials, lambda o: o.document.sha256 or ""):
            document = official.document
            if official.content is None:
                failures.append(
                    DocumentFailure(
                        "the JSON has no converted content (promote a conversion first)",
                        document.origin,
                        document.sha256 or "",
                    )
                )
            else:
                found.append(ExperimentFile(document, True, official.conversion_id, official))
        return FileResolution(found, failures)

    @staticmethod
    def run(
        source: Source,
        store: RecordingStore,
        converter: Converter,
        chunker: SectionChunker,
        experiment: str,
        request: ExperimentRequest,
        resolution: FileResolution,
        on_progress: ProgressCallback,
    ) -> ExperimentOutcome:
        run = _Experiment(source, store, converter, chunker, experiment, request, resolution, on_progress)
        try:
            for file in resolution.files:
                run.document(file)
        except (SourceError, SinkError) as error:
            return ExperimentOutcome(run.results(), run.progress, str(error))
        return ExperimentOutcome(run.results(), run.progress)


type _Cut = list[tuple[SectionAssignment, list[ChunkPiece], float]]  # each section, its chunks and the seconds spent


class _Experiment:
    """The state of one experiment while it runs."""

    def __init__(
        self,
        source: Source,
        store: RecordingStore,
        converter: Converter,
        chunker: SectionChunker,
        experiment: str,
        request: ExperimentRequest,
        resolution: FileResolution,
        on_progress: ProgressCallback,
    ) -> None:
        self.source, self.store, self.converter, self.chunker = source, store, converter, chunker
        self.experiment, self.request, self.resolution, self.on_progress = experiment, request, resolution, on_progress
        self.failures = list(resolution.failures)
        self.progress = ExperimentProgress(files=len(resolution.files), errors=len(self.failures))
        self.strategies: dict[str, _Group] = {}
        self.rules: dict[str, _Group] = {}
        self.conversion_seconds = self.chunking_seconds = 0.0

    def results(self) -> ExperimentResults:
        return ExperimentResults(
            documents=len(self.resolution.files),
            converted=self.progress.converted,
            reused=self.progress.reused,
            errors=self.progress.errors,
            conversion_seconds=round(self.conversion_seconds, 3),
            chunking_seconds=round(self.chunking_seconds, 3),
            by_strategy={k: g.result() for k, g in self.strategies.items()},
            by_rule={k: g.result() for k, g in self.rules.items()},
            failures=self.failures,
        )

    def advance(self, **changes: int) -> None:
        self.progress = advanced(self.progress, **changes)
        self.store.save(ExperimentGraph.progress(self.experiment, self.progress))
        self.on_progress(self.progress)

    def document(self, file: ExperimentFile) -> None:
        """Converts it (or reuses its conversion), cuts its sections by the plan and records it; a failure is
        recorded and the experiment goes on."""
        converted = self.converted(file)
        if converted is None:
            return
        content, reused = converted
        if self.request.plan is None:  # conversion only (feature 028)
            self.record(file, reused, [], 0.0, chunked=False)
            return
        try:
            cut = self.cut(content, self.request.plan)
            self.record(file, reused, cut, sum(seconds for _, _, seconds in cut))
        except (ConversionError, DocumentError) as error:
            self.fail(file, reused, str(error) or type(error).__name__)
            return
        self.tally(cut)

    def converted(self, file: ExperimentFile) -> tuple[ConvertedDocument, bool] | None:
        """The document organized by titles and whether it was reused; None if Docling failed (already recorded)."""
        document, sha256 = file.document, file.document.sha256 or ""
        if file.official is not None:  # an official JSON: its EXP_DOCUMENTO is made sure of, never converted again
            self.store.save(ExperimentGraph.restored_conversion(file.official, now()))
            if file.official.content is not None:
                return file.official.content, True
        elif file.reused and (stored := self.store.conversion(file.conversion_id)) is not None:
            return stored, True
        start = time.monotonic()
        try:
            content = self.source.content(document)
            converted = self.converter.convert(document.name, content, self.request.conversion)
        except (DocumentError, ConversionError) as error:
            self.fail_conversion(file, str(error) or type(error).__name__)
            return None
        seconds = time.monotonic() - start
        self.conversion_seconds += seconds
        self.store.save(
            ExperimentGraph.conversion(document, sha256, self.request.conversion, converted, None, seconds, now())
        )
        return converted, False

    def cut(self, content: ConvertedDocument, plan: Plan) -> _Cut:
        """Each section with the strategy its rule gives; ConversionError if a chunk is over its max_tokens."""
        cut: _Cut = []
        for assignment in Planner.assign(content, plan):
            start = time.monotonic()
            pieces = self.chunker.chunk(assignment.section, assignment.parameters)
            limit = assignment.parameters.max_tokens
            if limit is not None and any(p.tokens > limit for p in pieces):
                raise ConversionError(f"section {assignment.index}: a chunk has more than {limit} tokens")
            cut.append((assignment, pieces, time.monotonic() - start))
        return cut

    def record(self, file: ExperimentFile, reused: bool, cut: _Cut, spent: float, chunked: bool = True) -> None:
        """Stores the document in the experiment (its sections and chunks, if any) and moves the progress on."""
        pieces = [(assignment, chunks) for assignment, chunks, _ in cut]
        document, sha256 = file.document, file.document.sha256 or ""
        self.store.save(
            ExperimentGraph.document(
                self.experiment, document, sha256, file.conversion_id, reused, pieces, None, spent, chunked=chunked
            )
        )
        self.chunking_seconds += spent
        self.advance(
            done=1,
            converted=0 if reused else 1,
            reused=1 if reused else 0,
            sections=len(cut),
            chunks=sum(len(chunks) for _, chunks, _ in cut),
        )

    def tally(self, cut: _Cut) -> None:
        """Adds a stored document's sections to its strategy's and its rule's results."""
        for assignment, pieces, seconds in cut:
            rule = rule_name(assignment.rule)
            for key, groups in ((assignment.parameters.strategy.value, self.strategies), (rule, self.rules)):
                group = groups.setdefault(key, _Group())
                group.sections += 1
                group.tokens += [p.tokens for p in pieces]
                group.seconds += seconds

    def fail_conversion(self, file: ExperimentFile, error: str) -> None:
        """Docling (or ingesta) failed: the failed conversion is recorded too."""
        document, sha256 = file.document, file.document.sha256 or ""
        self.store.save(ExperimentGraph.conversion(document, sha256, self.request.conversion, None, error, 0.0, now()))
        self.fail(file, False, error)

    def fail(self, file: ExperimentFile, reused: bool, error: str) -> None:
        """Records a document that failed in the experiment."""
        document, sha256 = file.document, file.document.sha256 or ""
        self.failures.append(DocumentFailure(error, document.origin, sha256))
        self.store.save(
            ExperimentGraph.document(self.experiment, document, sha256, file.conversion_id, reused, [], error, 0)
        )
        self.advance(errors=1, done=1)
