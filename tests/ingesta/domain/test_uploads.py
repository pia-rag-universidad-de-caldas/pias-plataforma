"""Uploads (feature 049): the folder and name of an uploaded file, what is refused and how it is saved."""

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest

from ingesta.adapters import LocalFileAdapter, create_adapter
from ingesta.config import sqlite_url
from ingesta.domain import Discovery, Uploads
from ingesta.models import IncomingFile, MemoryStoreError, ORMAdapter, Upload, UploadState
from ingesta.repository import DbFileRepository, DbUploadRepository
from ingesta.tables import TABLES

PDF = b"%PDF" + b"x" * 2000
WHEN = datetime(2026, 11, 10, 14, 3, 22, 123456)
WEEK_BASE = datetime(2024, 2, 1)


@pytest.mark.parametrize(
    ("day", "week"), [(1, "Semana_01"), (7, "Semana_01"), (8, "Semana_02"), (28, "Semana_04"), (29, "Semana_05")]
)
def test_the_week_is_the_seven_days_block_of_the_month(day: int, week: str) -> None:
    assert Uploads.folder("023560", WEEK_BASE.replace(day=day)) == f"2024/02_Febrero/{week}/023560"


def test_the_stored_name_carries_the_corpus_upload_prefix() -> None:
    assert Uploads.stored_name("a.pdf", WHEN) == "2026-11-10-14.03.22.123456_a.pdf"


@pytest.mark.parametrize(
    ("sent", "clean"),
    [
        ("../../x.pdf", "x.pdf"),
        ("C:\\Users\\yo\\informe final.pdf", "informe_final.pdf"),
        ("a\x00b\n.pdf", "ab.pdf"),
        ('dos:"puntos"?.docx', "dos__puntos__.docx"),
    ],
)
def test_a_name_loses_its_folders_and_unsafe_characters(sent: str, clean: str) -> None:
    assert Uploads.clean_name(sent) == clean


@pytest.mark.parametrize(
    ("name", "size", "reason"),
    [
        ("", 2000, "oculto"),
        ("..", 2000, "oculto"),
        (".oculto.pdf", 2000, "oculto"),
        ("a.txt", 2000, "txt"),
        ("sin_extension", 2000, "sin_extension"),
        ("a.pdf", 10, "vacío"),
        ("x" * 300 + ".pdf", 2000, "bytes"),
    ],
)
def test_a_problem_says_why_a_file_is_refused(name: str, size: int, reason: str) -> None:
    problem = Uploads.problem(name, size)
    assert problem is not None and reason in problem


@pytest.mark.parametrize("name", ["a.pdf", "b.DOC", "c.docx"])
def test_pdf_doc_and_docx_are_accepted(name: str) -> None:
    assert Uploads.problem(name, 2000) is None


FULLWIDTH = "".join(chr(0xFF10 + int(d)) for d in "023560")  # digits for str.isdigit, not for a folder


@pytest.mark.parametrize(("code", "valid"), [("023560", True), ("000000", True), ("23560", False), (FULLWIDTH, False)])
def test_a_code_is_six_ascii_digits(code: str, valid: bool) -> None:
    assert Uploads.valid_code(code) is valid


@pytest.fixture
def memory(tmp_path: Path) -> Iterator[ORMAdapter]:
    data = create_adapter(sqlite_url(str(tmp_path / "m.sqlite3")), TABLES)
    yield data
    data.close()


def test_two_equal_files_in_one_upload_save_one(tmp_path: Path, memory: ORMAdapter) -> None:
    base = LocalFileAdapter(str(tmp_path / "base"))
    files = [IncomingFile("a.pdf", PDF), IncomingFile("b.pdf", PDF)]
    first, second = Uploads.save(base, DbFileRepository(memory), DbUploadRepository(memory), "023560", files, WHEN)
    assert first.estado == UploadState.SAVED and second.estado == UploadState.EXISTS and second.ruta == first.ruta
    assert [u.origen for u in DbUploadRepository(memory).all()] == [first.ruta]


def test_the_same_name_twice_never_overwrites(tmp_path: Path, memory: ORMAdapter) -> None:
    base = LocalFileAdapter(str(tmp_path / "base"))
    files = [IncomingFile("a.pdf", PDF), IncomingFile("a.pdf", PDF + b"2")]
    first, second = Uploads.save(base, DbFileRepository(memory), DbUploadRepository(memory), "023560", files, WHEN)
    assert first.ruta and second.ruta and first.ruta != second.ruta and second.ruta.endswith("__1.pdf")
    assert (tmp_path / "base" / first.ruta).read_bytes() == PDF
    assert Discovery.read_structure(second.ruta, len(PDF)).complete


class _BrokenUploads:
    def insert(self, upload: Upload) -> None:
        raise MemoryStoreError("down")

    def with_hash(self, sha256: str) -> list[Upload]:
        return []

    def all(self) -> list[Upload]:
        return []


def test_a_file_that_could_not_be_recorded_is_deleted(tmp_path: Path, memory: ORMAdapter) -> None:
    base = LocalFileAdapter(str(tmp_path / "base"))
    with pytest.raises(MemoryStoreError):
        Uploads.save(base, DbFileRepository(memory), _BrokenUploads(), "023560", [IncomingFile("a.pdf", PDF)], WHEN)
    assert not list((tmp_path / "base").rglob("*.pdf"))
