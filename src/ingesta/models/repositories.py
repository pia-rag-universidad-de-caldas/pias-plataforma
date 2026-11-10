"""Repositories: the only thing the domain knows about the memory."""

from collections.abc import Iterable
from typing import Protocol

from .concepts import FileMetadata
from .entities import CategoryDefinition, FileCategory, FileRecord, Run, Upload


class FileRepository(Protocol):
    def processed_origins(self) -> set[str]: ...

    def find(self, origin: str) -> FileRecord | None:
        """The record of that origin, or None if it isn't registered."""
        ...

    def with_hash(self, sha256: str) -> list[FileRecord]:
        """The records with that content (several if it was ingested more than once), by origin."""
        ...

    def all(self) -> list[FileRecord]: ...

    def insert(self, record: FileRecord) -> None:
        """Raises MemoryStoreError if it could not be stored."""
        ...

    def without_hash(self) -> list[FileRecord]: ...

    def save_hashes(self, hashes: Iterable[tuple[str, str]]) -> None:
        """Receives (origin, sha256) pairs."""
        ...

    def without_metadata(self) -> list[FileRecord]:
        """Records from before feature 009, without file system metadata."""
        ...

    def save_metadata(self, metadata: Iterable[tuple[str, FileMetadata]]) -> None:
        """Receives (origin, metadata) pairs."""
        ...

    def update_location(self, origin: str, file_type: str, target: str) -> None: ...

    def with_repeated_hash(self) -> list[FileRecord]:
        """All the records whose sha256 appears more than once."""
        ...


class CategoryRepository(Protocol):
    def sync_catalog(self, definitions: Iterable[CategoryDefinition]) -> None:
        """Makes the `categorias` catalog equal to the definitions (adds and updates)."""
        ...

    def all(self) -> list[FileCategory]: ...

    def add(self, rows: Iterable[FileCategory]) -> None: ...

    def remove(self, pairs: Iterable[tuple[str, str]]) -> None:
        """Receives (origin, category) pairs."""
        ...

    def mark_main(self, rows: Iterable[FileCategory]) -> None:
        """Updates the `principal` field of existing rows."""
        ...

    def origins_with(self, category: str) -> set[str]:
        """Origins of the files that have that category (main or not)."""
        ...


class RunRepository(Protocol):
    def start(self, start: str, action: str) -> int: ...

    def finish(self, run_id: int, end: str, new: int, skipped: int, errors: int) -> None: ...

    def last_finished(self) -> Run | None:
        """The last run that finished (the one with the latest `fin`), or None if none ever finished."""
        ...


class UploadRepository(Protocol):
    """The files uploaded through the API (feature 049)."""

    def insert(self, upload: Upload) -> None:
        """Raises MemoryStoreError if it could not be stored."""
        ...

    def with_hash(self, sha256: str) -> list[Upload]: ...

    def all(self) -> list[Upload]:
        """Newest first."""
        ...
