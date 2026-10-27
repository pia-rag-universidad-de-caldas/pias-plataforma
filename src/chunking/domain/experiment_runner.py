"""ExperimentRunner: one chunking experiment (feature 025). Resolves its files, converts each one (or reuses the
conversion stored with the same fingerprint), assigns a strategy to each section by the plan, cuts the sections and
records everything in the graph, document by document. A problem with one document is recorded and the experiment
goes on; only ingesta or data failing stops it."""

import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime

from chunking.config import GRAPH_PAGE_SIZE
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
    ExperimentStore,
    FileResolution,
    GroupResult,
    JsonSelection,
    OfficialDocument,
    SectionAssignment,
    SectionChunker,
    SinkError,
    SourceError,
    rule_name,
)
from chunking.models import ChunkSource as Source

from .experiment_graph import ExperimentGraph
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


class ExperimentRunner:
    @staticmethod
    def resolve(source: Source, store: ExperimentStore, request: ExperimentRequest, per_page: int) -> FileResolution:
        """The files that enter (in order, each once) and whether their conversion already exists."""
        files = request.files
        if files.from_json is not None:
            return ExperimentRunner._official(store, files.from_json)
        failures: list[DocumentFailure] = []
        documents = []
        if files.sha256s:
            for sha256 in dict.fromkeys(files.sha256s):
                try:
                    documents.append(source.find(sha256))
                except DocumentError as error:
                    failures.append(DocumentFailure(str(error), None, sha256))
        elif files.from_experiment:
            for used in store.documents(files.from_experiment):
                document = store.source(used.conversion_id)
                if document is None:
                    failures.append(
                        DocumentFailure("its conversion is no longer in the graph", used.origin, used.sha256)
                    )
                else:
                    documents.append(document)
        elif files.filter is not None and files.pages is not None:
            pages = files.pages
            for page in source.pages(files.filter, files.per_page or per_page, pages.first, pages.last):
                documents += page
        elif files.filter is not None:
            for page in source.pages(files.filter, files.per_page or per_page):
                if files.limit is None:
                    documents += page
                    continue
                documents += page[: files.limit - len(documents)]
                if len(documents) >= files.limit:
                    break
        found: list[ExperimentFile] = []
        seen: set[str] = set()
        for document in documents:
            if not document.sha256:
                failures.append(DocumentFailure("ingesta has no sha256 for it", document.origin, None))
            elif document.sha256 not in seen:
                seen.add(document.sha256)
                conversion_id = ExperimentGraph.conversion_id(document.sha256, request.conversion)
                found.append(ExperimentFile(document, store.has_conversion(conversion_id), conversion_id))
        return FileResolution(found, failures)

    @staticmethod
    def _official(store: ExperimentStore, selection: JsonSelection) -> FileResolution:
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
        seen: set[str] = set()
        for official in officials:
            document, sha256 = official.document, official.document.sha256 or ""
            if sha256 in seen:
                continue
            seen.add(sha256)
            if official.content is None:
                failures.append(
                    DocumentFailure(
                        "the JSON has no converted content (promote a conversion first)", document.origin, sha256
                    )
                )
            else:
                found.append(ExperimentFile(document, True, official.conversion_id, official))
        return FileResolution(found, failures)

    @staticmethod
    def run(
        source: Source,
        store: ExperimentStore,
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


class _Experiment:
    """The state of one experiment while it runs."""

    def __init__(
        self,
        source: Source,
        store: ExperimentStore,
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
        self.progress = replace(
            self.progress, **{name: getattr(self.progress, name) + value for name, value in changes.items()}
        )
        self.store.save(ExperimentGraph.progress(self.experiment, self.progress))
        self.on_progress(self.progress)

    def fail(self, file: ExperimentFile, conversion_id: str, reused: bool, error: str, conversion: bool) -> None:
        """Records a document that failed (and its failed conversion, if that is what failed)."""
        document, sha256 = file.document, file.document.sha256 or ""
        self.failures.append(DocumentFailure(error, document.origin, sha256))
        if conversion:
            batch = ExperimentGraph.conversion(document, sha256, self.request.conversion, None, error, 0.0, now())
            self.store.save(batch)
        self.store.save(
            ExperimentGraph.document(self.experiment, document, sha256, conversion_id, reused, [], error, 0)
        )
        self.advance(errors=1, done=1)

    def document(self, file: ExperimentFile) -> None:
        document, sha256, conversion_id = file.document, file.document.sha256 or "", file.conversion_id
        if file.official is not None:  # an official JSON: its EXP_DOCUMENTO is made sure of, never converted again
            converted: ConvertedDocument | None = file.official.content
            self.store.save(ExperimentGraph.restored_conversion(file.official, now()))
        else:
            converted = self.store.conversion(conversion_id) if file.reused else None
        reused = converted is not None
        if converted is None:
            start = time.monotonic()
            try:
                content = self.source.content(document)
                converted = self.converter.convert(document.name, content, self.request.conversion)
            except (DocumentError, ConversionError) as error:
                self.fail(file, conversion_id, reused, str(error) or type(error).__name__, conversion=True)
                return
            seconds = time.monotonic() - start
            self.conversion_seconds += seconds
            self.store.save(
                ExperimentGraph.conversion(document, sha256, self.request.conversion, converted, None, seconds, now())
            )
        if self.request.plan is None:  # conversion only (feature 028)
            self.store.save(
                ExperimentGraph.document(
                    self.experiment, document, sha256, conversion_id, reused, [], None, 0.0, chunked=False
                )
            )
            self.advance(done=1, converted=0 if reused else 1, reused=1 if reused else 0)
            return
        plan = self.request.plan
        cut: list[tuple[SectionAssignment, list[ChunkPiece]]] = []
        timed: list[tuple[SectionAssignment, list[ChunkPiece], float]] = []
        try:
            for assignment in Planner.assign(converted, plan):
                start = time.monotonic()
                pieces = self.chunker.chunk(assignment.section, assignment.parameters)
                limit = assignment.parameters.max_tokens
                if limit is not None and any(p.tokens > limit for p in pieces):
                    raise ConversionError(f"section {assignment.index}: a chunk has more than {limit} tokens")
                timed.append((assignment, pieces, time.monotonic() - start))
            cut = [(a, p) for a, p, _ in timed]
            spent = sum(t for _, _, t in timed)
            self.store.save(
                ExperimentGraph.document(self.experiment, document, sha256, conversion_id, reused, cut, None, spent)
            )
        except (ConversionError, DocumentError) as error:
            self.fail(file, conversion_id, reused, str(error) or type(error).__name__, conversion=False)
            return
        self.chunking_seconds += spent
        for assignment, pieces, seconds in timed:  # counted only once the document is stored
            rule = rule_name(assignment.rule)
            for key, groups in ((assignment.parameters.strategy.value, self.strategies), (rule, self.rules)):
                group = groups.setdefault(key, _Group())
                group.sections += 1
                group.tokens += [p.tokens for p in pieces]
                group.seconds += seconds
        self.advance(
            done=1,
            converted=0 if reused else 1,
            reused=1 if reused else 0,
            sections=len(cut),
            chunks=sum(len(p) for _, p in cut),
        )
