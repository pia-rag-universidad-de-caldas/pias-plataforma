"""Duplicates by content (Duplicates) and the reason of a repeated upload (Repetitions.reason)."""

from dataclasses import replace

from ingesta.domain import Duplicates, Repetitions
from ingesta.models import FileRecord, Reason

BASE = FileRecord(
    origen="2024/01/Semana_01/020055/a.pdf",
    destino="vigentes/pdf/a.pdf",
    anio=2024,
    mes="01",
    mes_num=1,
    semana="Semana_01",
    codigo="020055",
    nombre="a.pdf",
    tipo="pdf",
    bytes=5000,
    modificado="2024-01-01T00:00:00",
    procesado_en="2024-02-01T00:00:00",
    accion="copiado",
    sha256="h1",
    completo=True,
)


def test_the_last_modified_is_the_original_and_groups_go_by_recoverable_space() -> None:
    old = replace(BASE, origen="old.pdf", modificado="2024-01-01T00:00:00")
    new = replace(BASE, origen="new.pdf", modificado="2024-03-01T00:00:00")
    big = [replace(BASE, origen=f"big{i}.pdf", sha256="h2", bytes=90000) for i in range(2)]
    groups = Duplicates.group([old, new, *big])
    assert [g.sha256 for g in groups] == ["h2", "h1"]
    assert groups[1].original.origen == "new.pdf" and [c.origen for c in groups[1].copies] == ["old.pdf"]
    assert Duplicates.summarize(groups).recuperable == 90000 + 5000


def test_empty_files_and_files_without_hash_never_group() -> None:
    empty = [replace(BASE, origen=f"e{i}", bytes=0, sha256="e3b0") for i in range(3)]
    unhashed = [replace(BASE, origen=f"u{i}", sha256=None) for i in range(2)]
    assert Duplicates.group([*empty, *unhashed]) == []


def test_new_in_run_points_to_the_file_processed_first() -> None:
    before = replace(BASE, origen="before.pdf", destino="v/before.pdf", procesado_en="2024-01-01")
    now_a = replace(BASE, origen="a.pdf", destino="v/a.pdf", procesado_en="2024-05-01", modificado="2024-06-01")
    groups = Duplicates.group([before, now_a])
    [found] = Duplicates.new_in_run(groups, ["a.pdf"])
    assert (found.new, found.previous) == ("v/a.pdf", "v/before.pdf")


def test_the_first_reason_that_holds_wins() -> None:
    other = replace(BASE, origen="b.pdf")
    assert Repetitions.reason(BASE, other) is Reason.EXACT_COPY
    no_piaa = replace(other, sha256="h9", nombre="SIN_PIAA.pdf")
    assert Repetitions.reason(BASE, no_piaa) is Reason.NO_PIAA
    assert Repetitions.reason(BASE, replace(other, sha256="h9", tipo="docx")) is Reason.OTHER_FORMAT
    prefixed = replace(other, sha256="h9", nombre="2025-01-28-16.16.41.000000_A.PDF")
    assert Repetitions.reason(BASE, prefixed) is Reason.SAME_NAME
    assert Repetitions.reason(BASE, replace(other, sha256="h9", nombre="z.pdf")) is Reason.OTHER_NAME


def test_an_empty_previous_upload_is_never_an_exact_copy() -> None:
    empty = replace(BASE, bytes=0)
    assert Repetitions.reason(empty, replace(BASE, origen="b.pdf", bytes=0)) is not Reason.EXACT_COPY


def test_repeated_codes_skip_the_unassigned_one() -> None:
    a = replace(BASE, origen="a.pdf", codigo="000000")
    b = replace(BASE, origen="b.pdf", codigo="000000", modificado="2024-02-01T00:00:00")
    c = replace(BASE, origen="c.pdf", modificado="2024-02-01T00:00:00")
    [repeated] = Repetitions.group([a, b, BASE, c])
    assert (repeated.code, [u.record.origen for u in repeated.uploads]) == ("020055", [BASE.origen, "c.pdf"])
    assert repeated.uploads[1].seconds == 31 * 86400
