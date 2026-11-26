"""Ingestion.check (feature 030): what a source has and why it can't be ingested, on temporary folders."""

from collections.abc import Callable
from pathlib import Path

from ingesta.adapters import LocalFileAdapter
from ingesta.domain import Ingestion
from ingesta.models import IssueCode, SourceKind

type Write = Callable[..., None]


def _codes(root: Path, processed: set[str] | None = None, overlaps: bool = False) -> list[IssueCode]:
    check, _ = Ingestion.check(LocalFileAdapter(str(root)), SourceKind.FOLDER, processed or set(), overlaps)
    return [p.codigo for p in check.problemas]


def test_missing_folder(tmp_path: Path) -> None:
    check, plan = Ingestion.check(LocalFileAdapter(str(tmp_path / "nope")), SourceKind.FOLDER, set())
    assert not check.encontrada and check.estado == "error" and plan is None
    assert [p.codigo for p in check.problemas] == [IssueCode.NOT_FOUND]


def test_a_file_is_not_a_folder(tmp_path: Path, write_file: Write) -> None:
    write_file(tmp_path, "file.pdf")
    assert _codes(tmp_path / "file.pdf") == [IssueCode.NOT_A_FOLDER]


def test_empty_and_only_hidden(tmp_path: Path, write_file: Write) -> None:
    assert _codes(tmp_path) == [IssueCode.EMPTY]
    write_file(tmp_path, ".DS_Store", b"x")
    assert _codes(tmp_path) == [IssueCode.ONLY_HIDDEN]


def test_without_the_expected_structure(tmp_path: Path, write_file: Write) -> None:
    write_file(tmp_path, "loose.pdf")
    write_file(tmp_path, "docs/other.docx")
    assert _codes(tmp_path) == [IssueCode.NO_STRUCTURE]


def test_overlapping_the_ingesta_folder(tmp_path: Path, write_file: Write) -> None:
    write_file(tmp_path, "2024/11/Semana_04/671047/piaa.pdf")
    assert _codes(tmp_path, overlaps=True) == [IssueCode.OVERLAPS_INGEST]


def test_some_incomplete_and_nothing_new(tmp_path: Path, write_file: Write) -> None:
    write_file(tmp_path, "2024/11/Semana_04/671047/piaa.pdf")
    write_file(tmp_path, "loose.pdf")
    check, plan = Ingestion.check(LocalFileAdapter(str(tmp_path)), SourceKind.FOLDER, set())
    assert check.estado == "advertencia" and plan is not None
    assert (check.archivos, check.completos, check.incompletos, check.nuevos) == (2, 1, 1, 2)
    assert check.tipos == {"pdf": 2} and check.ejemplos_incompletos == ["loose.pdf"]
    assert [p.codigo for p in check.problemas] == [IssueCode.SOME_INCOMPLETE]
    done = {"2024/11/Semana_04/671047/piaa.pdf", "loose.pdf"}
    assert _codes(tmp_path, done) == [IssueCode.SOME_INCOMPLETE, IssueCode.NOTHING_NEW]
