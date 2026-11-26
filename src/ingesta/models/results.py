"""What an ingestion returns so its caller can report it."""

from dataclasses import dataclass, field

from .concepts import SourceFile
from .raw import RawSummary


@dataclass(frozen=True)
class OrganizationPlan:
    """What is in base/ compared with the memory."""

    found: list[SourceFile]
    new: list[SourceFile]
    ignored: list[str]  # relative paths in base/ of hidden files (.DS_Store, Office ~lock...)

    @property
    def already_in_memory(self) -> int:
        return len(self.found) - len(self.new)


@dataclass(frozen=True)
class FileFailure:
    origin: str  # relative path in base/: identifies the file in the memory
    error: str
    target: str | None = None  # relative path in ingesta/, if it was already known


@dataclass
class RunResult:
    origins: list[str] = field(default_factory=list)  # processed in this run, in order
    failures: list[FileFailure] = field(default_factory=list)

    @property
    def processed(self) -> int:
        return len(self.origins)


@dataclass(frozen=True)
class Relocation:
    current_target: str  # relative path in ingesta/
    new_folder: str  # relative folder in ingesta/ it goes to


@dataclass(frozen=True)
class CategoryChanges:
    """Rows of `archivos_categorias` that Organization.register_categories had to touch."""

    added: int
    removed: int
    main_changed: int


@dataclass(frozen=True)
class DuplicatesSummary:
    """Also part of GET /stats (DuplicatesReport.resumen): the field names are JSON keys."""

    grupos: int
    copias: int
    recuperable: int  # bytes


@dataclass(frozen=True)
class NewDuplicate:
    """A file of a run whose content had already been processed before."""

    new: str  # target of the new file
    previous: str  # target of the file that already had that content


@dataclass(frozen=True)
class Placement:
    """What Ingestion.place did (or would do, with simulate): relocations, category changes and the counts."""

    relocated: list[Relocation]
    changes: CategoryChanges | None  # None with simulate: the memory isn't touched
    main: dict[str, int]  # files per main category (folder)
    every: dict[str, int]  # files with each category (a file can have several)


@dataclass(frozen=True)
class IngestionOutcome:
    """What Ingestion.run did: the copy run, the placement and the duplicates of the corpus afterwards."""

    run: RunResult
    hashes_filled: int  # old records whose hash was missing
    metadata_filled: int  # old records whose metadata was missing
    placement: Placement
    duplicates: DuplicatesSummary
    new_duplicates: list[NewDuplicate]
    raw: RawSummary | None = None  # what was published in data (feature 042); None without data
