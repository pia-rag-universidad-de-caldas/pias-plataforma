"""Table of the files uploaded through the API (implements models.UploadRepository, feature 049)."""

from ingesta.models import Filter, Operator, ORMAdapter, Upload


class DbUploadRepository:
    def __init__(self, data: ORMAdapter) -> None:
        self._data = data

    def insert(self, upload: Upload) -> None:
        self._data.create(upload)

    def with_hash(self, sha256: str) -> list[Upload]:
        return self._data.search(Upload, (Filter("sha256", Operator.EQUAL, sha256),), order=("origen",))

    def all(self) -> list[Upload]:
        return list(reversed(self._data.search(Upload, order=("subido_en", "origen"))))
