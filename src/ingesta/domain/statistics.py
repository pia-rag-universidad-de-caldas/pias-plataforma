"""Statistics of the memory for the report.

- The date charts (year, month, growth) use only files with complete structure; everything else (totals, types,
  codes, duplicates, empty files) uses all of them.
- The repeated PIAA per year come from repetitions.py (only complete ones, without the unassigned code).
- The least frequent types are grouped into "otros" so there are enough colors.
- The duplicates are the same groups `organize` reports (see duplicates.py).
"""

from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar

from ingesta.config import (
    ALMOST_EMPTY_THRESHOLD,
    EMPTY_FOLDER,
    MAX_TYPES,
    TOP_DUPLICATES,
    TOP_EMPTY,
)
from ingesta.models import (
    Category,
    CleanupReport,
    DuplicateGroup,
    DuplicateGroupReport,
    DuplicatesReport,
    EmptyFilesReport,
    FileRecord,
    RepeatedCode,
    ReportData,
    SmallFile,
    YearComparison,
    YearRow,
    YearsComparison,
)
from ingesta.utils import numeric_summary

from .classification import Classifier
from .duplicates import Duplicates
from .naming import Naming
from .repetitions import Repetitions

GroupType = Callable[[str], str]  # type -> the same type or "otros"


@dataclass(frozen=True)
class _ByYear:
    by_type: defaultdict[int, Counter[str]]  # year -> files per type
    size_by_type: defaultdict[int, Counter[str]]  # year -> bytes per type
    by_month: defaultdict[int, Counter[int]]  # year -> files per month (1-12)

    @property
    def years(self) -> list[int]:
        return sorted(self.by_type)


class Statistics:
    """Only static methods: builds the report data; `build` joins the sections."""

    OTHERS: ClassVar[str] = "otros"  # report data: values stay as they are
    NO_YEAR: ClassVar[str] = "sin año"

    @staticmethod
    def _change(current: float, previous: float | None) -> float | None:
        return None if not previous else (current - previous) / previous * 100

    @staticmethod
    def _types(records: list[FileRecord]) -> tuple[Counter[str], list[str], GroupType]:
        """Count per type, the report types (the MAX_TYPES most frequent and "otros" if needed) and the function
        that groups the rest into "otros"."""
        count_by_type = Counter(r.tipo for r in records)
        main_types = [t for t, _ in count_by_type.most_common(MAX_TYPES)]
        types = [*main_types, Statistics.OTHERS] if len(count_by_type) > len(main_types) else main_types

        def group_type(file_type: str) -> str:
            return file_type if file_type in main_types else Statistics.OTHERS

        return count_by_type, types, group_type

    @staticmethod
    def _by_year(records: list[FileRecord], group_type: GroupType) -> _ByYear:
        """Counts per year of the files with complete structure (the date charts)."""
        by_year = _ByYear(defaultdict(Counter), defaultdict(Counter), defaultdict(Counter))
        for r in records:
            if not r.completo or r.anio is None:  # a complete one always has a year
                continue
            g = group_type(r.tipo)
            by_year.by_type[r.anio][g] += 1
            by_year.size_by_type[r.anio][g] += r.bytes
            if r.mes_num:
                by_year.by_month[r.anio][r.mes_num] += 1
        return by_year

    @staticmethod
    def year_comparison(records: list[FileRecord]) -> YearsComparison:
        """The report sections «Por año» and «Comparación entre años», with the same numbers as `build`."""
        _, types, group_type = Statistics._types(records)
        return Statistics._years(types, Statistics._by_year(records, group_type))

    @staticmethod
    def _years(types: list[str], by_year: _ByYear) -> YearsComparison:
        years = by_year.years
        return YearsComparison(
            anios=years,
            tipos=types,
            filas_anios=Statistics._year_rows(years, by_year.by_type, by_year.size_by_type, by_year.by_month),
            archivos_anio_tipo={y: [by_year.by_type[y][t] for t in types] for y in years},
            bytes_tipo_anio={t: [by_year.size_by_type[y][t] for y in years] for t in types},
            archivos_anio_mes={y: [by_year.by_month[y][m] for m in range(1, 13)] for y in years},
        )

    @staticmethod
    def year(records: list[FileRecord], year: int) -> YearComparison | None:
        """The comparison between years of a single year (its growth is against the previous year); None if there
        are no complete files of that year."""
        comparison = Statistics.year_comparison(records)
        if year not in comparison.anios:
            return None
        i = comparison.anios.index(year)
        return YearComparison(
            fila=comparison.filas_anios[i],
            tipos=comparison.tipos,
            archivos_por_tipo=comparison.archivos_anio_tipo[year],
            bytes_por_tipo=[comparison.bytes_tipo_anio[t][i] for t in comparison.tipos],
            archivos_por_mes=comparison.archivos_anio_mes[year],
        )

    @staticmethod
    def _year_rows(
        years: list[int],
        by_year_type: dict[int, Counter[str]],
        size_year_type: dict[int, Counter[str]],
        by_year_month: dict[int, Counter[int]],
    ) -> list[YearRow]:
        """A year with fewer than 12 months with data is partial: its total is not comparable, so the average per
        month with data is compared too."""
        rows: list[YearRow] = []
        for year in years:
            files, months = by_year_type[year].total(), len(by_year_month[year])
            average = files / (months or 1)
            previous = rows[-1] if rows else None
            rows.append(
                YearRow(
                    anio=year,
                    archivos=files,
                    bytes=size_year_type[year].total(),
                    meses_activos=months,
                    parcial=months < 12,
                    promedio_mes=average,
                    crecimiento=Statistics._change(files, previous.archivos if previous else None),
                    crecimiento_mes=Statistics._change(average, previous.promedio_mes if previous else None),
                )
            )
        return rows

    @staticmethod
    def _empties(records: list[FileRecord], types: list[str], group_type: GroupType) -> EmptyFilesReport:
        small = sorted((r for r in records if Naming.is_empty(r.bytes)), key=lambda r: (r.bytes, r.destino))
        empty = Counter(group_type(r.tipo) for r in small if r.bytes == 0)
        almost = Counter(group_type(r.tipo) for r in small if r.bytes > 0)
        return EmptyFilesReport(
            umbral=ALMOST_EMPTY_THRESHOLD,
            carpeta=EMPTY_FOLDER,
            vacios=empty.total(),
            casi_vacios=almost.total(),
            vacios_por_tipo=[empty[t] for t in types],
            casi_vacios_por_tipo=[almost[t] for t in types],
            menores=[SmallFile(destino=r.destino, tipo=group_type(r.tipo), bytes=r.bytes) for r in small[:TOP_EMPTY]],
        )

    @staticmethod
    def _duplicates(
        groups: list[DuplicateGroup],
        records: list[FileRecord],
        types: list[str],
        years: list[int],
        group_type: GroupType,
    ) -> DuplicatesReport:
        copies = [c for g in groups for c in g.copies]
        by_type = Counter(group_type(c.tipo) for c in copies)
        by_year = Counter(c.anio for c in copies)
        copy_years = sorted({*years, *(y for y in by_year if y is not None)})
        copies_by_year = [(str(y), by_year[y]) for y in copy_years]
        if by_year[None]:
            copies_by_year.append((Statistics.NO_YEAR, by_year[None]))
        return DuplicatesReport(
            resumen=Duplicates.summarize(groups),
            grupos_multi_codigo=sum(1 for g in groups if len({r.codigo for r in g.members}) > 1),
            sin_hash=sum(1 for r in records if r.sha256 is None),
            copias_por_tipo=[by_type[t] for t in types],
            copias_por_anio=copies_by_year,
            principales=[
                DuplicateGroupReport(
                    sha256=g.sha256,
                    bytes=g.bytes,
                    tipo=group_type(g.original.tipo),
                    rutas=[r.destino for r in g.members],
                    anios=sorted({r.anio for r in g.members if r.anio is not None}),
                )
                for g in groups[:TOP_DUPLICATES]
            ],
        )

    @staticmethod
    def _deduplicated(records: list[FileRecord], groups: list[DuplicateGroup]) -> list[FileRecord]:
        """The non-empty files, with one representative per content (the codes are counted on these)."""
        without_empty = [r for r in records if r.bytes >= ALMOST_EMPTY_THRESHOLD]

        deduplicated: list[FileRecord] = []
        seen_sha: set[str] = set()
        for g in groups:
            if not g.members:
                continue
            if g.sha256 in seen_sha:
                continue
            representative = next((r for r in g.members if r.bytes >= ALMOST_EMPTY_THRESHOLD), None)
            if representative is not None:
                deduplicated.append(representative)
                seen_sha.add(g.sha256)
        for r in without_empty:
            if r.sha256 is None or r.sha256 not in seen_sha:
                deduplicated.append(r)
        return deduplicated

    @staticmethod
    def _cleanup(records: list[FileRecord]) -> CleanupReport:
        """Same numbers as the ingesta/ folders: it comes from the same classification."""
        count = Counter(c.main for c in Classifier.classify(records).values())  # one folder per file
        without_empty = len(records) - count[Category.EMPTY]
        only_supported = without_empty - count[Category.UNSUPPORTED]
        without_duplicates = only_supported - count[Category.HASH_DUPLICATE]
        return CleanupReport(
            total=len(records),
            vacios=count[Category.EMPTY],
            sin_vacios=without_empty,
            extranios=count[Category.UNSUPPORTED],
            solo_soportados=only_supported,
            hash_duplicados=count[Category.HASH_DUPLICATE],
            sin_duplicados=without_duplicates,
            codigos_duplicados=count[Category.CODE_DUPLICATE],
            incompletos=count[Category.INCOMPLETE],
            aptos_chunking=count[Category.CHUNKABLE],
        )

    @staticmethod
    def build(records: list[FileRecord], groups: list[DuplicateGroup], repeated: list[RepeatedCode]) -> ReportData:
        """Main function: joins all the report sections."""
        count_by_type, types, group_type = Statistics._types(records)
        other_types = sorted(set(count_by_type) - set(types))

        sizes_by_type: defaultdict[str, list[int]] = defaultdict(list)
        for r in records:
            sizes_by_type[group_type(r.tipo)].append(r.bytes)

        comparison = Statistics._years(types, Statistics._by_year(records, group_type))
        codes = Counter(r.codigo for r in Statistics._deduplicated(records, groups) if r.codigo)
        duplicated_codes = [(code, amount) for code, amount in codes.items() if amount > 1]
        incomplete = [r for r in records if not r.completo]
        return ReportData(
            archivos=len(records),
            bytes=sum(r.bytes for r in records),
            total_codigos=len(codes),
            total_tipos=len(count_by_type),
            tipos=types,
            otros={t: count_by_type[t] for t in other_types},
            resumen_por_tipo={t: numeric_summary(sizes_by_type[t]) for t in types},
            codigos_principales=sorted(duplicated_codes, key=lambda item: (-item[1], item[0])),
            anios=comparison.anios,
            archivos_anio_tipo=comparison.archivos_anio_tipo,
            bytes_tipo_anio=comparison.bytes_tipo_anio,
            archivos_anio_mes=comparison.archivos_anio_mes,
            filas_anios=comparison.filas_anios,
            duplicados=Statistics._duplicates(groups, records, types, comparison.anios, group_type),
            vacios=Statistics._empties(records, types, group_type),
            limpieza=Statistics._cleanup(records),
            incompletos=len(incomplete),
            bytes_incompletos=sum(r.bytes for r in incomplete),
            repetidos=Repetitions.build_report(records, repeated),
        )
