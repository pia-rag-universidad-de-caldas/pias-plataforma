"""FileAdapter (feature 013): read and write files under a root, with relative paths as text. The implementation lives
in adapters/, the only package that uses pathlib, shutil, os and stat."""

from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from dataclasses import dataclass


class FileError(Exception):
    """File system failure (doesn't exist, no permission, disk full...). Raised by the FileAdapter so the domain
    handles it without depending on os or pathlib."""


@dataclass(frozen=True)
class FileInfo:
    """What the file system knows about a file. Timestamps in seconds since the epoch."""

    path: str  # relative to the adapter root, with "/"
    bytes: int
    modified: float  # mtime
    created: float | None  # None if the system doesn't provide it (Linux)
    changed: float  # ctime
    accessed: float  # atime
    permissions: str  # octal, "644"


class FileReader(ABC):
    """Reading files under a root (feature 013): what an ingestion source needs (feature 030: a source is read-only,
    an external SQL database will implement only this). Paths are relative to the root, as text with "/"; "" is the
    root. Every failure is raised as FileError."""

    @abstractmethod
    def absolute(self, path: str = "") -> str:
        """The full path, to show it or pass it to another tool (for example, the SQLite URL)."""

    @abstractmethod
    def exists(self, path: str = "") -> bool: ...

    @abstractmethod
    def is_file(self, path: str) -> bool: ...

    @abstractmethod
    def is_dir(self, path: str = "") -> bool: ...

    @abstractmethod
    def list_files(self) -> list[FileInfo]:
        """All the regular files under the root, at any level; skips the ones that can't be read."""

    @abstractmethod
    def info(self, path: str) -> FileInfo: ...

    @abstractmethod
    def hash(self, path: str) -> str:
        """sha256 of the content."""

    @abstractmethod
    def read_chunks(self, path: str, chunk_size: int = 1 << 20) -> Iterator[bytes]:
        """The content in blocks of up to `chunk_size` bytes, to stream it without loading it whole (feature 022).
        Opens the file right away (FileError if it doesn't exist, can't be read or falls outside the root) and closes
        it when the iteration ends or the iterator is closed."""


class FileWriter(ABC):
    """Changing files under a root (ingesta/; base/ is only read). Paths and errors as in FileReader."""

    @abstractmethod
    def make_dir(self, path: str = "") -> None:
        """Creates the folder and the missing ones above it; doesn't fail if it already exists."""

    @abstractmethod
    def free_name(self, folder: str, name: str) -> str:
        """folder/name, or folder/name__N.ext if it already exists, so nothing is overwritten."""

    @abstractmethod
    def copy_from(self, source: FileReader, path: str, target: str) -> str:
        """Copies `path` from `source` to `target` and returns the sha256 of what was written. Atomic: if interrupted,
        no half-written file is left with the final name. From an adapter of the same kind it also keeps the dates
        and permissions."""

    @abstractmethod
    def write_new(self, target: str, chunks: Iterable[bytes]) -> str:
        """Writes the blocks as `target` and returns the sha256 of what was written (feature 049: an upload). Atomic
        as copy_from, with a hidden temporary name so a discovery running meanwhile doesn't take it, and never
        overwrites: FileError if `target` already exists."""

    @abstractmethod
    def move(self, path: str, target: str) -> None:
        """Renames inside the same root (replaces `target` if it exists)."""

    @abstractmethod
    def delete(self, path: str, missing_ok: bool = False) -> None: ...

    @abstractmethod
    def remove_empty_dirs(self, folder: str) -> None:
        """Deletes `folder` and the ones above it while they are empty, never deleting the root."""


class FileAdapter(FileReader, FileWriter):
    """Files under a root that can be read and changed: one adapter per folder (base/, ingesta/...)."""
