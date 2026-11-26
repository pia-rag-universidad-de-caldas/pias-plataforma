"""Statistics: the numbers of GET /stats, from records made by the test."""

import pytest

from ingesta.config import ALMOST_EMPTY_THRESHOLD, EMPTY_FOLDER, MAX_TYPES, TOP_DUPLICATES, TOP_EMPTY
from ingesta.domain import Duplicates, Repetitions, Statistics
from ingesta.models import FileRecord, ReportData

KB = 1024


def record(
    origin: str,
    year: int | None = 2024,
    month: int | None = 1,
    file_type: str = "pdf",
    size: int = 10 * KB,
    code: str | None = "020055",
    sha: str | None = None,
    complete: bool = True,
) -> FileRecord:
    return FileRecord(
        origen=origin,
        destino=f"x/{origin}",
        anio=year,
        mes=f"{month:02}_Mes" if month else None,
        mes_num=month,
        semana="Semana_01",
        codigo=code,
        nombre=origin,
        tipo=file_type,
        bytes=size,
        modificado="2024-01-01T00:00:00",
        procesado_en="2024-02-01T00:00:00",
        accion="copiado",
        sha256=sha,
        completo=complete,
    )


def build(*records: FileRecord) -> ReportData:
    files = list(records)
    return Statistics.build(files, Duplicates.group(files), Repetitions.group(files))


def test_nothing_gives_an_empty_report() -> None:
    report = build()
    assert (report.archivos, report.bytes, report.tipos, report.anios) == (0, 0, [], [])


def test_the_totals_count_every_file() -> None:
    report = build(record("a", size=2 * KB, code="1"), record("b", size=3 * KB, complete=False, code="2"))
    assert (report.archivos, report.bytes, report.total_codigos) == (2, 5 * KB, 2)


def test_only_the_most_frequent_types_have_their_own_name() -> None:
    files = [record(f"t{i}", file_type=f"t{i}") for i in range(MAX_TYPES + 2)]
    report = build(*files)
    assert len(report.tipos) == MAX_TYPES + 1
    assert report.tipos[-1] == "otros"
    assert sum(report.otros.values()) == 2
    assert report.total_tipos == MAX_TYPES + 2


def test_exactly_the_maximum_of_types_needs_no_others() -> None:
    report = build(*[record(f"t{i}", file_type=f"t{i}") for i in range(MAX_TYPES)])
    assert "otros" not in report.tipos


def test_the_sizes_are_summarized_by_type() -> None:
    report = build(record("a", size=2 * KB), record("b", size=4 * KB), record("c", file_type="doc", size=KB))
    assert report.resumen_por_tipo["pdf"].total == 6 * KB
    assert report.resumen_por_tipo["doc"].casos == 1


def test_the_date_charts_use_only_complete_files() -> None:
    report = build(record("a", year=2023), record("b", year=2024, complete=False))
    assert report.anios == [2023]


def test_a_complete_file_without_year_is_not_in_the_date_charts() -> None:
    assert build(record("a", year=None)).anios == []


def test_files_by_year_type_and_month() -> None:
    report = build(record("a", month=2), record("b", month=2), record("c", month=3, file_type="doc", code="9"))
    assert report.archivos_anio_tipo[2024] == [2, 1]
    assert report.archivos_anio_mes[2024][1:3] == [2, 1]
    assert report.bytes_tipo_anio == {"pdf": [20 * KB], "doc": [10 * KB]}


def test_a_month_out_of_a_file_doesnt_count_as_active() -> None:
    assert build(record("a", month=None)).filas_anios[0].meses_activos == 0


def test_a_year_row_says_files_bytes_and_average_per_active_month() -> None:
    [row] = build(record("a", month=1), record("b", month=1), record("c", month=2)).filas_anios
    assert (row.anio, row.archivos, row.bytes, row.meses_activos) == (2024, 3, 30 * KB, 2)
    assert row.promedio_mes == pytest.approx(1.5)


def test_a_year_with_fewer_than_twelve_months_is_partial() -> None:
    assert build(record("a")).filas_anios[0].parcial is True


def test_a_year_with_all_the_months_is_not_partial() -> None:
    report = build(*[record(f"m{m}", month=m) for m in range(1, 13)])
    assert report.filas_anios[0].parcial is False


def test_the_first_year_has_no_growth() -> None:
    row = build(record("a")).filas_anios[0]
    assert (row.crecimiento, row.crecimiento_mes) == (None, None)


def test_growth_is_against_the_previous_year() -> None:
    report = build(record("a", year=2023), record("b", year=2024), record("c", year=2024))
    assert report.filas_anios[1].crecimiento == pytest.approx(100)
    assert report.filas_anios[1].crecimiento_mes == pytest.approx(100)


def test_empty_and_almost_empty_files_are_told_apart() -> None:
    report = build(record("a", size=0), record("b", size=ALMOST_EMPTY_THRESHOLD - 1), record("c"))
    empties = report.vacios
    assert (empties.vacios, empties.casi_vacios) == (1, 1)
    assert (empties.umbral, empties.carpeta) == (ALMOST_EMPTY_THRESHOLD, EMPTY_FOLDER)
    assert (empties.vacios_por_tipo, empties.casi_vacios_por_tipo) == ([1], [1])


def test_a_file_of_the_threshold_is_not_almost_empty() -> None:
    assert build(record("a", size=ALMOST_EMPTY_THRESHOLD)).vacios.casi_vacios == 0


def test_the_smallest_files_come_first_and_only_the_top_ones() -> None:
    report = build(*[record(f"f{i:03}", size=i) for i in range(TOP_EMPTY + 3, 0, -1)])
    assert len(report.vacios.menores) == TOP_EMPTY
    assert report.vacios.menores[0].bytes == 1


def test_a_group_of_copies_is_summarized() -> None:
    report = build(record("a", sha="h", code="1"), record("b", sha="h", code="2", year=2023), record("c"))
    duplicates = report.duplicados
    assert duplicates.grupos_multi_codigo == 1
    assert duplicates.copias_por_tipo == [1]
    assert duplicates.sin_hash == 1
    assert duplicates.principales[0].sha256 == "h"
    assert duplicates.principales[0].anios == [2023, 2024]


def test_a_group_with_a_single_code_is_not_multi_code() -> None:
    assert build(record("a", sha="h"), record("b", sha="h")).duplicados.grupos_multi_codigo == 0


def test_copies_are_counted_by_year() -> None:
    report = build(record("a", sha="h", year=2023), record("b", sha="h", year=2024))
    assert report.duplicados.copias_por_anio == [("2023", 1), ("2024", 0)]  # the newest is the original


def test_copies_without_a_year_are_counted_apart() -> None:
    report = build(
        record("a", sha="h", year=2024, complete=False, month=None),
        record("b", sha="h", year=None, complete=False, month=None),
    )
    assert report.duplicados.copias_por_anio == [("sin año", 1)]


def test_only_the_top_groups_are_listed() -> None:
    files = [record(f"{i}-{n}", sha=f"h{i}") for i in range(TOP_DUPLICATES + 1) for n in "ab"]
    assert len(build(*files).duplicados.principales) == TOP_DUPLICATES


def test_codes_count_one_file_per_content() -> None:
    report = build(record("a", sha="h"), record("b", sha="h"))
    assert report.total_codigos == 1
    assert report.codigos_principales == []


def test_an_empty_file_doesnt_count_for_its_code() -> None:
    assert build(record("a", size=0)).total_codigos == 0


def test_the_codes_with_most_files_come_first() -> None:
    report = build(
        record("a", code="1", sha="x"),
        record("b", code="1", sha="y"),
        record("c", code="2", sha="z"),
        record("d", code="2", sha="w"),
        record("e", code="2", sha="v"),
        record("f", code="3", sha="u"),
    )
    assert report.codigos_principales == [("2", 3), ("1", 2)]


def test_codes_with_the_same_files_go_by_code() -> None:
    report = build(
        record("a", code="2", sha="x"),
        record("b", code="2", sha="y"),
        record("c", code="1", sha="z"),
        record("d", code="1", sha="w"),
    )
    assert [code for code, _ in report.codigos_principales] == ["1", "2"]


def test_the_incomplete_files_are_counted_apart() -> None:
    report = build(record("a", complete=False, size=3 * KB), record("b"))
    assert (report.incompletos, report.bytes_incompletos) == (1, 3 * KB)


def test_the_cleanup_has_the_numbers_of_the_folders() -> None:
    cleanup = build(
        record("vacio", size=0, code="1"),
        record("raro", file_type="txt", code="2"),
        record("a", sha="h", code="3"),
        record("b", sha="h", code="3"),
        record("incompleto", complete=False, code=None),
        record("viejo", code="5", sha="v"),
        record("nuevo", code="5", sha="n"),
    ).limpieza
    assert (cleanup.total, cleanup.vacios, cleanup.sin_vacios) == (7, 1, 6)
    assert (cleanup.extranios, cleanup.solo_soportados) == (1, 5)
    assert (cleanup.hash_duplicados, cleanup.sin_duplicados) == (1, 4)
    assert (cleanup.codigos_duplicados, cleanup.incompletos) == (1, 1)
    assert cleanup.aptos_chunking == 2


def test_the_comparison_between_years_has_the_numbers_of_the_report() -> None:
    files = [record("a", year=2023), record("b", year=2024)]
    comparison = Statistics.year_comparison(files)
    report = build(*files)
    assert (comparison.anios, comparison.filas_anios) == (report.anios, report.filas_anios)


def test_a_year_with_its_own_numbers() -> None:
    found = Statistics.year([record("a", year=2023, size=KB), record("b", year=2024, month=3, size=2 * KB)], 2024)
    assert found is not None
    assert (found.fila.anio, found.archivos_por_tipo, found.bytes_por_tipo) == (2024, [1], [2 * KB])
    assert found.archivos_por_mes[2] == 1


def test_a_year_without_complete_files_is_none() -> None:
    assert Statistics.year([record("a", year=2023)], 2024) is None
