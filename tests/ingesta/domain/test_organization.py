"""Organization: copying is never half done. On temporary folders with a real SQLite memory."""

import hashlib
from collections.abc import Iterator
from pathlib import Path

import pytest

from ingesta.adapters import LocalFileAdapter, create_adapter
from ingesta.config import sqlite_url
from ingesta.domain import Classifier, Discovery, Organization
from ingesta.models import (
    Category,
    FileError,
    FileInfo,
    FileReader,
    FileRecord,
    MemoryStoreError,
    ORMAdapter,
    RunResult,
)
from ingesta.repository import DbCategoryRepository, DbFileRepository, DbRunRepository
from ingesta.tables import TABLES

PDF = b"%PDF-1.7 " + b"x" * 4000
A = "2024/01_Ene/Semana_01/020055/a.pdf"
B = "2024/01_Ene/Semana_02/020056/b.pdf"


class FailingCopy(LocalFileAdapter):
    """Fails copying one origin, or deleting any file of base/."""

    def __init__(self, root: str, fail_copy: str = "", fail_delete: bool = False) -> None:
        super().__init__(root)
        self.fail_copy, self.fail_delete = fail_copy, fail_delete

    def copy_from(self, source: FileReader, path: str, target: str) -> str:
        if path == self.fail_copy:
            raise FileError("disk full")
        return super().copy_from(source, path, target)

    def delete(self, path: str, missing_ok: bool = False) -> None:
        if self.fail_delete:
            raise FileError("read-only")
        super().delete(path, missing_ok)


class FailingInsert(DbFileRepository):
    def __init__(self, data: ORMAdapter, fail: str) -> None:
        super().__init__(data)
        self.fail = fail

    def insert(self, record: FileRecord) -> None:
        if record.origen == self.fail:
            raise MemoryStoreError("locked")
        super().insert(record)


@pytest.fixture
def folders(tmp_path: Path) -> tuple[Path, Path]:
    base, ingest = tmp_path / "base", tmp_path / "ingesta"
    for relative in (A, B):
        (base / relative).parent.mkdir(parents=True)
        (base / relative).write_bytes(PDF + relative.encode())
    ingest.mkdir()
    return base, ingest


def run(
    base: Path, ingest: Path, repo_fail: str = "", copy_fail: str = "", move: bool = False
) -> tuple[RunResult, list[str], list[FileRecord]]:
    data = create_adapter(sqlite_url(str(ingest / "m.sqlite3")), TABLES)
    try:
        repo = FailingInsert(data, repo_fail)
        source = LocalFileAdapter(str(base))
        target = FailingCopy(str(ingest), fail_copy=copy_fail)
        plan = Discovery.plan(source, repo.processed_origins())
        result = Organization.execute(plan, source, target, repo, DbRunRepository(data), source if move else None)
        return result, sorted(r.origen for r in repo.all()), repo.all()
    finally:
        data.close()


def files(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*.pdf"))


def test_a_failed_copy_doesnt_stop_the_run_nor_leave_anything(folders: tuple[Path, Path]) -> None:
    base, ingest = folders
    result, registered, _ = run(base, ingest, copy_fail=A)
    assert registered == [B]
    assert [f.origin for f in result.failures] == [A]
    assert files(ingest) == ["vigentes/pdf/2024-01_Ene-Semana_02-020056-b.pdf"]
    assert not list(ingest.rglob("*.parcial"))


def test_a_failed_insert_deletes_its_copy_and_the_next_run_retries_it(folders: tuple[Path, Path]) -> None:
    base, ingest = folders
    _, registered, _ = run(base, ingest, repo_fail=A)
    assert registered == [B] and len(files(ingest)) == 1
    _, registered, _ = run(base, ingest)
    assert registered == [A, B] and len(files(ingest)) == 2


def test_move_deletes_the_original_only_after_registering(folders: tuple[Path, Path]) -> None:
    base, ingest = folders
    _, registered, records = run(base, ingest, repo_fail=A, move=True)
    assert registered == [B]
    assert (base / A).exists() and not (base / B).exists()  # A failed: its original stays
    assert [r.accion for r in records] == ["movido"]


def test_an_original_that_cant_be_deleted_stays_registered_as_copied(folders: tuple[Path, Path]) -> None:
    base, ingest = folders
    data = create_adapter(sqlite_url(str(ingest / "m.sqlite3")), TABLES)
    try:
        repo = DbFileRepository(data)
        source = FailingCopy(str(base), fail_delete=True)
        plan = Discovery.plan(source, set())
        result = Organization.execute(plan, source, LocalFileAdapter(str(ingest)), repo, DbRunRepository(data), source)
        assert sorted(result.not_deleted) == [A, B]
        assert {r.accion for r in repo.all()} == {"copiado"}
        assert (base / A).exists()
    finally:
        data.close()


def test_relocate_and_register_follow_the_classification(folders: tuple[Path, Path]) -> None:
    base, ingest = folders
    (base / B).write_bytes((base / A).read_bytes())  # B now repeats A's content and is newer
    data = create_adapter(sqlite_url(str(ingest / "m.sqlite3")), TABLES)
    try:
        repo, categories = DbFileRepository(data), DbCategoryRepository(data)
        target = LocalFileAdapter(str(ingest))
        source = LocalFileAdapter(str(base))
        Organization.execute(Discovery.plan(source, set()), source, target, repo, DbRunRepository(data), None)
        records = repo.all()
        classification = Classifier.classify(records)
        simulated = Organization.relocate(repo, records, classification, target, simulate=True)
        assert files(ingest) == sorted(
            f"vigentes/pdf/{n}" for n in ("2024-01_Ene-Semana_01-020055-a.pdf", "2024-01_Ene-Semana_02-020056-b.pdf")
        )
        assert [r.new_folder for r in simulated] == ["hash_duplicados/pdf"]
        Organization.relocate(repo, records, classification, target, simulate=False)
        assert files(ingest)[0].startswith("hash_duplicados/pdf/")
        categories.sync_catalog(Classifier.category_definitions())
        changes = Organization.register_categories(categories, classification)
        assert (changes.added, changes.removed) == (3, 0)  # A: hash duplicate; B: current + chunkable
        assert categories.origins_with(Category.CHUNKABLE.value) == {B}
        again = Organization.register_categories(categories, classification)
        assert (again.added, again.removed, again.main_changed) == (0, 0, 0)
    finally:
        data.close()


class OnlyReads(FileReader):
    """A source that isn't a local folder (an external database, feature 030): it can only be read."""

    def __init__(self, files: dict[str, bytes]) -> None:
        self._files = files

    def absolute(self, path: str = "") -> str:
        return f"db://{path}"

    def exists(self, path: str = "") -> bool:
        return not path or path in self._files

    def is_file(self, path: str) -> bool:
        return path in self._files

    def is_dir(self, path: str = "") -> bool:
        return not path

    def list_files(self) -> list[FileInfo]:
        return [self.info(path) for path in self._files]

    def info(self, path: str) -> FileInfo:
        return FileInfo(path, len(self._files[path]), 1.7e9, None, 1.7e9, 1.7e9, "644")

    def hash(self, path: str) -> str:
        return hashlib.sha256(self._files[path]).hexdigest()

    def read_text(self, path: str, encoding: str = "utf-8") -> str:
        return self._files[path].decode(encoding)

    def read_chunks(self, path: str, chunk_size: int = 1 << 20) -> Iterator[bytes]:
        content = self._files[path]
        return iter([content[i : i + 10] for i in range(0, len(content), 10)])


def test_a_read_only_source_is_copied_block_by_block(tmp_path: Path) -> None:
    source = OnlyReads({A: PDF})
    data = create_adapter(sqlite_url(str(tmp_path / "m.sqlite3")), TABLES)
    try:
        repo = DbFileRepository(data)
        plan = Discovery.plan(source, set())
        result = Organization.execute(plan, source, LocalFileAdapter(str(tmp_path)), repo, DbRunRepository(data), None)
        assert result.failures == [] and result.origins == [A]
        [record] = repo.all()
        assert record.sha256 == hashlib.sha256(PDF).hexdigest()
        assert (tmp_path / record.destino).read_bytes() == PDF
    finally:
        data.close()
