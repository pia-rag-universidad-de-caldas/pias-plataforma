"""Table of processed files (implements models.FileRepository) on top of the agnostic adapter."""

from collections.abc import Iterable
from dataclasses import replace

from ingesta.models import FileMetadata, FileRecord, Filter, MemoryStoreError, Operator, ORMAdapter


class DbFileRepository:
    def __init__(self, data: ORMAdapter) -> None:
        self._data = data

    def _read(self, origin: str) -> FileRecord:
        record = self._data.read(FileRecord, origin)
        if record is None:
            raise MemoryStoreError(f"the record {origin} doesn't exist")
        return record

    def _by_origin(self) -> dict[str, FileRecord]:
        """All the records at once, to change many without one read per row."""
        return {r.origen: r for r in self._data.search(FileRecord)}

    def find(self, origin: str) -> FileRecord | None:
        return self._data.read(FileRecord, origin)

    def with_hash(self, sha256: str) -> list[FileRecord]:
        return self._data.search(FileRecord, (Filter("sha256", Operator.EQUAL, sha256),), order=("origen",))

    def processed_origins(self) -> set[str]:
        return set(self._by_origin())

    def all(self) -> list[FileRecord]:
        return self._data.search(FileRecord, order=("origen",))

    def insert(self, record: FileRecord) -> None:
        self._data.create(record)  # one save per file: if the process is interrupted, nothing is lost

    def without_hash(self) -> list[FileRecord]:
        return self._data.search(FileRecord, (Filter("sha256", Operator.IS_NULL),), order=("origen",))

    def save_hashes(self, hashes: Iterable[tuple[str, str]]) -> None:
        hashes = list(hashes)
        if hashes:
            current = self._by_origin()
            self._data.update([replace(current[origin], sha256=sha) for origin, sha in hashes])

    def without_metadata(self) -> list[FileRecord]:
        return self._data.search(FileRecord, (Filter("permisos", Operator.IS_NULL),), order=("origen",))

    def save_metadata(self, metadata: Iterable[tuple[str, FileMetadata]]) -> None:
        # `modificado` is not touched: it was stored on ingest and it decides which file is newer.
        metadata = list(metadata)
        if not metadata:
            return
        current = self._by_origin()
        self._data.update(
            [
                replace(
                    current[origin],
                    creado=m.created,
                    cambiado=m.changed,
                    accedido=m.accessed,
                    permisos=m.permissions,
                    mime=m.mime,
                )
                for origin, m in metadata
            ]
        )

    def update_location(self, origin: str, file_type: str, target: str) -> None:
        self._data.update(replace(self._read(origin), tipo=file_type, destino=target))

    def with_repeated_hash(self) -> list[FileRecord]:
        return self._data.search(FileRecord, (Filter("sha256", Operator.REPEATED),), order=("origen",))
