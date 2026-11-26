"""RawSync (feature 042): which chunkable files are published in data as RAW, and what a publication does."""

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import replace

import pytest

from ingesta.domain import RawSync
from ingesta.domain.raw_sync import encoded_size
from ingesta.models import FileError, FileInfo, FileReader, FileRecord, RawFileRejected, RawPlan

RECORD = FileRecord(
    "2024/01/S/020055/a.pdf",
    "vigentes/pdf/a.pdf",
    2024,
    "01",
    1,
    "S",
    "020055",
    "a.pdf",
    "pdf",
    5000,
    "2024-01-01",
    "2024-01-02",
    "copiado",
    "h1",
    True,
)
OTHER = replace(RECORD, origen="2024/01/S/020056/b.pdf", destino="vigentes/pdf/b.pdf", sha256="h2")


class Store:
    def __init__(self, refuse: Sequence[str] = ()) -> None:
        self.sent: list[tuple[str, bytes]] = []
        self.retired: list[str] = []
        self._refuse = set(refuse)

    def publish(self, record: FileRecord, content: bytes, at: str) -> None:
        if record.sha256 in self._refuse:
            raise RawFileRejected("too big")
        self.sent.append((record.sha256 or "", content))

    def retire(self, sha256s: Sequence[str]) -> None:
        self.retired += sha256s

    def published(self) -> Mapping[str, bool]:
        return {}


class Files(FileReader):
    """Only read_chunks: the content of each destination, or FileError for those it doesn't have."""

    def __init__(self, contents: Mapping[str, bytes]) -> None:
        self._contents = contents

    def read_chunks(self, path: str, chunk_size: int = 1 << 20) -> Iterator[bytes]:
        if path not in self._contents:
            raise FileError(f"no {path}")
        yield self._contents[path]

    def absolute(self, path: str = "") -> str:
        raise NotImplementedError

    def exists(self, path: str = "") -> bool:
        raise NotImplementedError

    def is_file(self, path: str) -> bool:
        raise NotImplementedError

    def is_dir(self, path: str = "") -> bool:
        raise NotImplementedError

    def list_files(self) -> list[FileInfo]:
        raise NotImplementedError

    def info(self, path: str) -> FileInfo:
        raise NotImplementedError

    def hash(self, path: str) -> str:
        raise NotImplementedError


def test_the_chunkable_files_data_doesnt_have_are_uploaded() -> None:
    plan = RawSync.plan([RECORD, OTHER], {RECORD.origen, OTHER.origen}, {"h1": True})
    assert ([r.sha256 for r in plan.upload], plan.already, plan.retire) == (["h2"], 1, [])


def test_a_raw_no_longer_current_is_uploaded_again_if_its_file_is_chunkable_again() -> None:
    assert [r.sha256 for r in RawSync.plan([RECORD], {RECORD.origen}, {"h1": False}).upload] == ["h1"]


def test_a_raw_whose_file_stopped_being_chunkable_is_retired_once() -> None:
    plan = RawSync.plan([RECORD], {RECORD.origen}, {"h1": True, "gone": True, "old": False})
    assert plan.retire == ["gone"]


def test_a_file_that_isnt_chunkable_or_without_hash_isnt_uploaded() -> None:
    no_hash = replace(OTHER, sha256=None)
    assert RawSync.plan([RECORD, no_hash], {no_hash.origen}, {}).upload == []


def test_a_publication_uploads_retires_and_counts() -> None:
    store = Store()
    plan = RawPlan([RECORD], 3, ["gone"])
    summary = RawSync.run(plan, store, Files({RECORD.destino: b"pdf"}), 1 << 30, "at")
    assert store.sent == [("h1", b"pdf")] and store.retired == ["gone"]
    assert (summary.subidos, summary.ya_estaban, summary.retirados, summary.fallidos) == (1, 3, 1, 0)


@pytest.mark.parametrize(
    ("files", "refuse", "limit"),
    [({}, (), 1 << 30), ({"vigentes/pdf/a.pdf": b"pdf"}, ("h1",), 1 << 30), ({"vigentes/pdf/a.pdf": b"pdf"}, (), 10)],
    ids=["unreadable", "refused by data", "too big"],
)
def test_a_file_that_fails_doesnt_stop_the_others(files: dict[str, bytes], refuse: tuple[str, ...], limit: int) -> None:
    store = Store(refuse)
    other = {**files, OTHER.destino: b"ok"} if limit > 10 else files
    summary = RawSync.run(RawPlan([RECORD, OTHER], 0, []), store, Files(other), limit, "at")
    assert summary.errores[0].sha256 == "h1"
    assert summary.fallidos == (1 if limit > 10 else 2)


def test_the_size_counts_the_base64_and_the_rest_of_the_batch() -> None:
    assert encoded_size(3 * 1024) == 4 * 1024 + 64 * 1024
