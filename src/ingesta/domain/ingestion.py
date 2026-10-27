"""Ingestion process (feature 030): check a source, copy what is new and classify the whole corpus.

The steps of `organize`, without printing: the CLI and the API run them and each one reports through its own
IngestionObserver. The source is a FileReader: only `organize --move` gives its writer, to delete the originals.
"""

from collections import Counter
from typing import Literal

from ingesta.config import LEVELS, PROGRESS_EVERY
from ingesta.models import (
    Category,
    CategoryRepository,
    FileAdapter,
    FileError,
    FileFailure,
    FileReader,
    FileRepository,
    FileWriter,
    IngestionOutcome,
    IssueCode,
    IssueLevel,
    OrganizationPlan,
    Placement,
    RunRepository,
    SourceCheck,
    SourceIssue,
    SourceKind,
)

from .classification import Classifier
from .discovery import Discovery
from .duplicates import Duplicates
from .naming import Naming
from .organization import Organization

MAX_EXAMPLES = 10  # incomplete paths listed in a check
_STRUCTURE = "/".join(["<year>", "<month>", "<week>", "<code>", "<file>"][:LEVELS])


type Stage = Literal["hashes", "metadata", "copy"]


class IngestionObserver:
    """What a run tells whoever drives it (the console, the API's registry). Each method does nothing by default:
    override the ones you need."""

    def stage(self, name: Stage, total: int) -> None:
        """A step starts: filling the hash or the metadata of `total` old records, or copying `total` new files."""

    def filled(self, done: int, total: int) -> None:
        """Old records filled so far (hash or metadata, every HASH_BATCH)."""

    def copied(self, done: int, total: int) -> None:
        """New files processed so far (every `progress_every`)."""

    def failed(self, failure: FileFailure) -> None:
        """A file failed; the run goes on."""


def _issue(code: IssueCode, level: IssueLevel, message: str) -> SourceIssue:
    return SourceIssue(code, level, message)


class Ingestion:
    """Only static methods: check, place and run."""

    @staticmethod
    def check(
        source: FileReader, kind: SourceKind, processed: set[str], overlaps_ingest: bool = False
    ) -> tuple[SourceCheck, OrganizationPlan | None]:
        """What the source has and why it can't be ingested, if so; the plan only when it could be read."""
        location = source.absolute()
        if not source.exists():
            issue = _issue(IssueCode.NOT_FOUND, IssueLevel.ERROR, f"the folder doesn't exist: {location}")
            return SourceCheck(kind, location, False, IssueLevel.ERROR.value, problemas=[issue]), None
        if not source.is_dir():
            issue = _issue(IssueCode.NOT_A_FOLDER, IssueLevel.ERROR, f"it is a file, not a folder: {location}")
            return SourceCheck(kind, location, True, IssueLevel.ERROR.value, problemas=[issue]), None
        if overlaps_ingest:
            message = f"{location} is the ingesta folder, is inside it or contains it: it would copy into itself"
            issue = _issue(IssueCode.OVERLAPS_INGEST, IssueLevel.ERROR, message)
            return SourceCheck(kind, location, True, IssueLevel.ERROR.value, problemas=[issue]), None
        try:
            plan = Discovery.plan(source, processed)
        except FileError as e:
            issue = _issue(IssueCode.UNREADABLE, IssueLevel.ERROR, f"the folder could not be read: {e}")
            return SourceCheck(kind, location, True, IssueLevel.ERROR.value, problemas=[issue]), None

        complete = [f for f in plan.found if f.complete]
        incomplete = [f for f in plan.found if not f.complete]
        problems: list[SourceIssue] = []
        if not plan.found and not plan.ignored:
            problems.append(_issue(IssueCode.EMPTY, IssueLevel.ERROR, "the folder has no files"))
        elif not plan.found:
            message = f"the folder only has hidden files ({len(plan.ignored)}: .DS_Store, Office ~lock...)"
            problems.append(_issue(IssueCode.ONLY_HIDDEN, IssueLevel.ERROR, message))
        elif not complete:
            message = f"no file follows {_STRUCTURE}: it doesn't look like the expected folder"
            problems.append(_issue(IssueCode.NO_STRUCTURE, IssueLevel.ERROR, message))
        else:
            if incomplete:
                message = f"{len(incomplete)} files don't follow {_STRUCTURE}: they go to formato_incompleto/"
                problems.append(_issue(IssueCode.SOME_INCOMPLETE, IssueLevel.WARNING, message))
            if not plan.new:
                message = "every file is already in the memory: nothing to copy"
                problems.append(_issue(IssueCode.NOTHING_NEW, IssueLevel.WARNING, message))
        types = Counter(Naming.file_type(f.name) for f in plan.found)
        result = SourceCheck(
            kind,
            location,
            True,
            SourceCheck.state(problems),
            archivos=len(plan.found),
            ocultos=len(plan.ignored),
            completos=len(complete),
            incompletos=len(incomplete),
            nuevos=len(plan.new),
            ya_en_memoria=plan.already_in_memory,
            tipos=dict(types.most_common()),
            ejemplos_incompletos=[f.path for f in incomplete[:MAX_EXAMPLES]],
            problemas=problems,
        )
        return result, plan

    @staticmethod
    def place(repo: FileRepository, categories: CategoryRepository, ingest: FileAdapter, simulate: bool) -> Placement:
        """Classifies the whole memory, moves each file of ingesta/ to the folder of its main category and stores all
        its categories in archivos_categorias (with simulate it only says what it would do)."""
        records = repo.all()
        classification = Classifier.classify(records)
        relocated = Organization.relocate(repo, records, classification, ingest, simulate)
        changes = None
        if not simulate:
            categories.sync_catalog(Classifier.category_definitions())
            changes = Organization.register_categories(categories, classification)
        main = Counter(c.main for c in classification.values())
        every = Counter(cat for c in classification.values() for cat in c.categories)
        return Placement(
            relocated,
            changes,
            {c.value: main[c] for c in Category},
            {c.value: every[c] for c in Category},
        )

    @staticmethod
    def run(
        plan: OrganizationPlan,
        source: FileReader,
        ingest: FileAdapter,
        repo: FileRepository,
        runs: RunRepository,
        categories: CategoryRepository,
        observer: IngestionObserver | None = None,
        progress_every: int = PROGRESS_EVERY,
        move: FileWriter | None = None,
    ) -> IngestionOutcome:
        """Fills what old records miss, copies the new files, places the corpus and sums up the duplicates. `move` is
        the writer of the source when moving (the CLI's --move); the API never passes it: its source stays intact.
        An error with a file doesn't stop it (see Organization.execute)."""
        report = observer or IngestionObserver()
        hashes = repo.without_hash()
        if hashes:
            report.stage("hashes", len(hashes))
            Organization.fill_hashes(repo, ingest, hashes, report.filled, report.failed)
        metadata = repo.without_metadata()
        if metadata:
            report.stage("metadata", len(metadata))
            Organization.fill_metadata(repo, source, ingest, metadata, report.filled, report.failed)
        report.stage("copy", len(plan.new))
        result = Organization.execute(
            plan, source, ingest, repo, runs, move, report.copied, report.failed, progress_every
        )
        placement = Ingestion.place(repo, categories, ingest, simulate=False)
        groups = Duplicates.group(repo.with_repeated_hash())
        new_duplicates = Duplicates.new_in_run(groups, result.origins) if result.processed else []
        return IngestionOutcome(
            result, len(hashes), len(metadata), placement, Duplicates.summarize(groups), new_duplicates
        )
