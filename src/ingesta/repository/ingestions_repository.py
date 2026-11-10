"""Table of the ingestions started from the API (feature 039) on top of the agnostic adapter."""

from ingesta.models import IngestionRecord, ORMAdapter


class DbIngestionRepository:
    def __init__(self, data: ORMAdapter) -> None:
        self._data = data

    def save(self, record: IngestionRecord) -> None:
        if self._data.read(IngestionRecord, record.id) is None:
            self._data.create(record)
        else:
            self._data.update(record)

    def find(self, id: str) -> IngestionRecord | None:
        return self._data.read(IngestionRecord, id)

    def all(self) -> list[IngestionRecord]:
        """Newest first."""
        return list(reversed(self._data.search(IngestionRecord, order=("inicio",))))
