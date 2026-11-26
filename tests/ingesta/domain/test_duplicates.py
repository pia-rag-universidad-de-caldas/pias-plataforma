"""Duplicates by content (Duplicates): which file stays, which never group and what a run repeats."""

from dataclasses import replace
from typing import Any

import pytest

from ingesta.domain import Duplicates
from ingesta.models import FileRecord

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


def ordered_by_age(*records: FileRecord) -> list[str]:
    return [r.origen for r in sorted(records, key=Duplicates.age_key)]


@pytest.mark.parametrize(
    ("older", "newer"),
    [
        ({"anio": 2023}, {"anio": 2024}),
        ({"mes_num": 1}, {"mes_num": 2}),
        ({"semana": "Semana_2"}, {"semana": "Semana_10"}),  # natural order, not alphabetical
        ({"mes_num": None}, {"mes_num": 1}),
        ({"semana": None}, {"semana": "Semana_1"}),
    ],
)
def test_age_goes_from_the_oldest_to_the_newest(older: dict[str, Any], newer: dict[str, Any]) -> None:
    assert ordered_by_age(replace(BASE, origen="new", **newer), replace(BASE, origen="old", **older)) == ["old", "new"]


def test_a_file_with_an_unknown_year_counts_as_the_newest() -> None:
    assert ordered_by_age(replace(BASE, origen="unknown", anio=None), replace(BASE, origen="known")) == [
        "known",
        "unknown",
    ]


def test_on_the_same_date_the_age_goes_by_destination() -> None:
    assert ordered_by_age(replace(BASE, origen="b", destino="z"), replace(BASE, origen="a", destino="y")) == ["a", "b"]


@pytest.mark.parametrize(
    ("older", "newer"),
    [
        ({"anio": 2023}, {"anio": 2024}),
        ({"anio": None}, {"anio": 2024}),
        ({"mes_num": 1}, {"mes_num": 2}),
        ({"mes_num": None}, {"mes_num": 1}),
        ({"semana": "Semana_2"}, {"semana": "Semana_10"}),
        ({"semana": None}, {"semana": "Semana_1"}),
    ],
)
def test_with_the_same_modification_the_most_recent_folder_is_the_original(
    older: dict[str, Any], newer: dict[str, Any]
) -> None:
    [group] = Duplicates.group([replace(BASE, origen="old", **older), replace(BASE, origen="new", **newer)])
    assert group.original.origen == "new"


def test_a_group_has_the_size_of_its_files() -> None:
    [group] = Duplicates.group([replace(BASE, origen=name, bytes=7000) for name in "ab"])
    assert group.bytes == 7000


def test_a_file_of_one_byte_can_be_a_copy() -> None:
    assert len(Duplicates.group([replace(BASE, origen=name, bytes=1) for name in "ab"])) == 1
