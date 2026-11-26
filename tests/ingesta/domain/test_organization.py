"""Organization: copying is never half done. On temporary folders with a real SQLite memory."""

import hashlib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

import pytest

from ingesta.adapters import LocalFileAdapter, create_adapter
from ingesta.config import sqlite_url
from ingesta.domain import ClassificationMap, Classifier, Discovery, Organization
from ingesta.domain import organization as organization_module
from ingesta.models import (
    Category,
    FileError,
    FileInfo,
    FileMetadata,
    FileReader,
    FileRecord,
    FileRepository,
    MemoryStoreError,
    ORMAdapter,
    RunResult,
)
from ingesta.repository import DbCategoryRepository, DbFileRepository, DbRunRepository
from ingesta.tables import TABLES

PDF = b"%PDF-1.7 " + b"x" * 4000
A = "2024/01_Ene/Semana_01/020055/a.pdf"
B = "2024/01_Ene/Semana_02/020056/b.pdf"
RECORD = FileRecord(
    origen="o",
    destino="d",
    anio=2024,
    mes="01_Ene",
    mes_num=1,
    semana="Semana_01",
    codigo="020055",
    nombre="a.pdf",
    tipo="pdf",
    bytes=4000,
    modificado="2024-01-01T00:00:00",
    procesado_en="2024-02-01T00:00:00",
    accion="copiado",
    sha256=None,
    completo=True,
)


@dataclass(frozen=True)
class Executed:
    repo: DbFileRepository
    categories: DbCategoryRepository
    target: LocalFileAdapter
    ingest: Path
    classification: ClassificationMap


class FailingCopy(LocalFileAdapter):
    """Fails copying one origin."""

    def __init__(self, root: str, fail_copy: str = "") -> None:
        super().__init__(root)
        self.fail_copy = fail_copy

    def copy_from(self, source: FileReader, path: str, target: str) -> str:
        if path == self.fail_copy:
            raise FileError("disk full")
        return super().copy_from(source, path, target)


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
    base: Path, ingest: Path, repo_fail: str = "", copy_fail: str = ""
) -> tuple[RunResult, list[str], list[FileRecord]]:
    data = create_adapter(sqlite_url(str(ingest / "m.sqlite3")), TABLES)
    try:
        repo = FailingInsert(data, repo_fail)
        source = LocalFileAdapter(str(base))
        target = FailingCopy(str(ingest), fail_copy=copy_fail)
        plan = Discovery.plan(source, repo.processed_origins())
        result = Organization.execute(plan, source, target, repo, DbRunRepository(data))
        return result, sorted(r.origen for r in repo.all()), repo.all()
    finally:
        data.close()


def files(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*.pdf"))


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


@pytest.fixture
def executed(folders: tuple[Path, Path]) -> Iterator[Executed]:
    """Both files copied to vigentes/; B repeats A's content and is newer, so A has to go to hash_duplicados/."""
    base, ingest = folders
    (base / B).write_bytes((base / A).read_bytes())
    data = create_adapter(sqlite_url(str(ingest / "m.sqlite3")), TABLES)
    try:
        repo, categories = DbFileRepository(data), DbCategoryRepository(data)
        target, source = LocalFileAdapter(str(ingest)), LocalFileAdapter(str(base))
        Organization.execute(Discovery.plan(source, set()), source, target, repo, DbRunRepository(data))
        categories.sync_catalog(Classifier.category_definitions())
        yield Executed(repo, categories, target, ingest, Classifier.classify(repo.all()))
    finally:
        data.close()


def test_a_simulated_relocation_says_where_and_moves_nothing(executed: Executed) -> None:
    simulated = Organization.relocate(
        executed.repo, executed.repo.all(), executed.classification, executed.target, simulate=True
    )
    assert [r.new_folder for r in simulated] == ["hash_duplicados/pdf"]
    assert files(executed.ingest) == sorted(
        f"vigentes/pdf/{n}" for n in ("2024-01_Ene-Semana_01-020055-a.pdf", "2024-01_Ene-Semana_02-020056-b.pdf")
    )


def test_a_relocation_moves_the_file_to_the_folder_of_its_category(executed: Executed) -> None:
    Organization.relocate(executed.repo, executed.repo.all(), executed.classification, executed.target, simulate=False)
    assert files(executed.ingest)[0].startswith("hash_duplicados/pdf/")


def test_registering_adds_every_category_of_the_classification(executed: Executed) -> None:
    changes = Organization.register_categories(executed.categories, executed.classification)
    assert (changes.added, changes.removed) == (3, 0)  # A: hash duplicate; B: current + chunkable
    assert executed.categories.origins_with(Category.CHUNKABLE.value) == {B}


def test_registering_the_same_classification_again_changes_nothing(executed: Executed) -> None:
    Organization.register_categories(executed.categories, executed.classification)
    again = Organization.register_categories(executed.categories, executed.classification)
    assert (again.added, again.removed, again.main_changed) == (0, 0, 0)


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

    def read_chunks(self, path: str, chunk_size: int = 1 << 20) -> Iterator[bytes]:
        content = self._files[path]
        return iter([content[i : i + 10] for i in range(0, len(content), 10)])


def test_a_read_only_source_is_copied_block_by_block(tmp_path: Path) -> None:
    source = OnlyReads({A: PDF})
    data = create_adapter(sqlite_url(str(tmp_path / "m.sqlite3")), TABLES)
    try:
        repo = DbFileRepository(data)
        plan = Discovery.plan(source, set())
        result = Organization.execute(plan, source, LocalFileAdapter(str(tmp_path)), repo, DbRunRepository(data))
        assert result.failures == [] and result.origins == [A]
        [record] = repo.all()
        assert record.sha256 == hashlib.sha256(PDF).hexdigest()
        assert (tmp_path / record.destino).read_bytes() == PDF
    finally:
        data.close()


def test_a_file_that_failed_is_not_among_the_processed(folders: tuple[Path, Path]) -> None:
    base, ingest = folders
    result, _, _ = run(base, ingest, copy_fail=A)
    assert result.origins == [B]


class LosesTheCopy(DbFileRepository):
    """The memory refuses the file, and the copy is gone by the time it has to be deleted."""

    def __init__(self, data: ORMAdapter, ingest: Path) -> None:
        super().__init__(data)
        self._ingest = ingest

    def insert(self, record: FileRecord) -> None:
        (self._ingest / record.destino).unlink()
        raise MemoryStoreError("locked")


def test_a_copy_that_is_already_gone_doesnt_stop_the_run(folders: tuple[Path, Path]) -> None:
    base, ingest = folders
    data = create_adapter(sqlite_url(str(ingest / "m.sqlite3")), TABLES)
    try:
        source = LocalFileAdapter(str(base))
        plan = Discovery.plan(source, set())
        result = Organization.execute(
            plan, source, LocalFileAdapter(str(ingest)), LosesTheCopy(data, ingest), DbRunRepository(data)
        )
    finally:
        data.close()
    assert sorted(f.origin for f in result.failures) == [A, B]


@pytest.mark.parametrize(("every", "expected"), [(1, [(1, 2), (2, 2)]), (2, [(2, 2)]), (3, [])])
def test_progress_is_told_every_so_many_files(
    folders: tuple[Path, Path], every: int, expected: list[tuple[int, int]]
) -> None:
    base, ingest = folders
    told: list[tuple[int, int]] = []
    data = create_adapter(sqlite_url(str(ingest / "m.sqlite3")), TABLES)
    try:
        source = LocalFileAdapter(str(base))
        Organization.execute(
            Discovery.plan(source, set()),
            source,
            LocalFileAdapter(str(ingest)),
            DbFileRepository(data),
            DbRunRepository(data),
            on_progress=lambda done, total: told.append((done, total)),
            progress_every=every,
        )
    finally:
        data.close()
    assert told == expected


class Hashes:
    """As much of a repository as filling hashes uses."""

    def __init__(self) -> None:
        self.saves: list[list[tuple[str, str]]] = []

    def save_hashes(self, hashes: Iterable[tuple[str, str]]) -> None:
        self.saves.append(list(hashes))


class HashReader(LocalFileAdapter):
    def hash(self, path: str) -> str:
        return f"hash of {path}"


def test_old_hashes_are_saved_in_batches_and_progress_is_told_after_each(
    monkeypatch: pytest.MonkeyPatch, folders: tuple[Path, Path]
) -> None:
    monkeypatch.setattr(organization_module, "HASH_BATCH", 2)
    _, ingest = folders
    pending = [replace(RECORD, origen=f"o{i}", destino=f"d{i}") for i in range(3)]
    repo = Hashes()
    told: list[tuple[int, int]] = []
    Organization.fill_hashes(
        cast(FileRepository, repo), HashReader(str(ingest)), pending, lambda done, total: told.append((done, total))
    )
    assert [[origin for origin, _ in batch] for batch in repo.saves] == [["o0", "o1"], ["o2"]]
    assert told == [(2, 3)]


def test_registering_marks_as_main_the_category_that_decides_the_folder(executed: Executed) -> None:
    Organization.register_categories(executed.categories, executed.classification)
    mains = {row.origen: row.categoria for row in executed.categories.all() if row.principal}
    assert mains == {A: Category.HASH_DUPLICATE.value, B: Category.CHUNKABLE.value}


def test_a_relocation_of_a_copy_that_is_gone_only_corrects_the_memory(executed: Executed) -> None:
    records = executed.repo.all()
    stale = next(r for r in records if r.origen == A)
    (executed.ingest / stale.destino).unlink()
    Organization.relocate(executed.repo, records, executed.classification, executed.target, simulate=False)
    found = executed.repo.find(A)
    assert found is not None
    assert found.destino.startswith("hash_duplicados/pdf/")


def test_old_metadata_is_read_from_the_original_with_its_mime(folders: tuple[Path, Path]) -> None:
    base, ingest = folders
    saved: list[tuple[str, FileMetadata]] = []

    class Metadata:
        def save_metadata(self, metadata: Iterable[tuple[str, FileMetadata]]) -> None:
            saved.extend(metadata)

    record = replace(RECORD, origen=A, destino="d", nombre="a.pdf")
    Organization.fill_metadata(
        cast(FileRepository, Metadata()), LocalFileAdapter(str(base)), LocalFileAdapter(str(ingest)), [record]
    )
    assert [(origin, meta.mime) for origin, meta in saved] == [(A, "application/pdf")]
