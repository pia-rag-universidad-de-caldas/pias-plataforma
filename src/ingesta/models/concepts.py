"""Domain concepts: they live in memory while a command runs and are not stored as they are."""

from dataclasses import dataclass
from enum import Enum

from .entities import FileRecord


@dataclass(frozen=True)
class SourceFile:
    """A file found in base/.

    Complete: base/<year>/<month>/<week>/<code>/<name>. Otherwise, the fields are filled as far as the folders
    go (only if the first one is a year) and the rest stays None.
    """

    path: str  # relative path inside base/; identifies the file in the memory
    folders: tuple[str, ...]  # folders between base/ and the file
    name: str
    complete: bool
    bytes: int
    year: str | None = None
    month: str | None = None
    week: str | None = None
    code: str | None = None


@dataclass(frozen=True)
class FileMetadata:
    """File system metadata: the FileRecord fields that Organization.fill_metadata fills in."""

    modified: str  # mtime, ISO
    created: str | None  # None if the system does not provide it
    changed: str  # ctime, ISO
    accessed: str  # atime, ISO
    permissions: str  # octal, "644"
    mime: str | None  # None if the extension is unknown


class Category(Enum):
    """Label of a file (see domain.classification). A file can have several; the order of the enumeration is
    the priority: the first one it has is the main one and decides its folder in ingesta/.

    The values are stored in the memory (archivos_categorias) and printed: do not change them."""

    EMPTY = "vacio"  # 0 B or almost empty
    UNSUPPORTED = "extranio"  # type that is not chunked (not pdf/doc/docx)
    HASH_DUPLICATE = "hash_duplicado"  # same sha256 as a newer one
    CODE_DUPLICATE = "codigo_duplicado"  # same code as the current file of that code
    INCOMPLETE = "incompleto"  # without the year/month/week/code structure
    CHUNKABLE = "apto_chunking"  # current, pdf/doc/docx and not empty: what Docling chunks
    CURRENT = "vigente"  # neither a hash nor a code duplicate (can be empty or unsupported)


@dataclass(frozen=True)
class FileClassification:
    """All the categories of a file and the main one (the one with the highest priority)."""

    main: Category
    categories: frozenset[Category]


@dataclass(frozen=True)
class DuplicateGroup:
    """Files with the same content. The original (the one that stays) is the last modified."""

    sha256: str
    bytes: int
    original: FileRecord
    copies: tuple[FileRecord, ...]

    @property
    def members(self) -> tuple[FileRecord, ...]:
        return (self.original, *self.copies)

    @property
    def recoverable(self) -> int:
        return self.bytes * len(self.copies)


class Reason(Enum):
    """Why a file repeats the code of the previous upload of the same year (see domain.repetitions). The order
    of the enumeration is the order in which they are checked: the first one that holds wins.

    The values are part of GET /stats/repeated: do not change them."""

    EXACT_COPY = "copia exacta"  # same sha256
    NO_PIAA = "SIN_PIAA"  # one of the two is the SIN_PIAA template
    OTHER_FORMAT = "otro formato"  # different type
    SAME_NAME = "mismo nombre, otro contenido"  # same name without the upload date prefix
    OTHER_NAME = "otro nombre y contenido"


@dataclass(frozen=True)
class RepeatedUpload:
    """A file of a repeated code, compared with the previous upload of the same code and year."""

    record: FileRecord
    reason: Reason | None  # None on the first upload
    seconds: float | None  # since the previous upload; None on the first one


@dataclass(frozen=True)
class RepeatedCode:
    """A code with two or more files in the same year, in upload order."""

    year: int
    code: str
    uploads: tuple[RepeatedUpload, ...]
