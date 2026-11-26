"""Repeated PIAA: codes with two or more files in the same year.

- A PIAA is a code within a year; only files with complete structure count.
- The unassigned code (UNASSIGNED_CODE) groups different courses: it doesn't count as repeated and is reported
  apart.
- The files of each code are sorted by upload (Duplicates.newness_key) and each one is compared with the previous:
  its reason is the first one of Reason that holds and its interval, the seconds between both `modificado`.
- Times: between consecutive uploads (per year and per reason) and from the first to the last of each code.
- Leftovers by hash: files of the year that repeat the content (sha256, without the 0 B ones) of another one of the
  same year.
"""

import math
import re
import statistics
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from datetime import datetime
from itertools import pairwise
from typing import ClassVar

from ingesta.config import NO_PIAA_MARK, TOP_REPEATED, UNASSIGNED_CODE
from ingesta.models import (
    FileRecord,
    NumericSummary,
    Reason,
    RepeatedCode,
    RepeatedCodeReport,
    RepeatedReport,
    RepeatedUpload,
    RepeatedYearRow,
)
from ingesta.utils import numeric_summary

from .duplicates import Duplicates

CodeYearKey = tuple[int, str]


class Repetitions:
    """Only static methods: the repeated PIAA rules under one name."""

    # (up to how many seconds, label); the last one has no limit. The labels are report data.
    INTERVALS: ClassVar[list[tuple[float, str]]] = [
        (60, "< 1 min"),
        (600, "1–10 min"),
        (3600, "10–60 min"),
        (86400, "1–24 h"),
        (7 * 86400, "1–7 días"),
        (30 * 86400, "7–30 días"),
        (math.inf, "> 30 días"),
    ]
    MAX_COUNT: ClassVar[int] = 6  # the codes with more files are grouped in "6+"

    # Prefix the upload system adds to the names: "2025-01-28-16.16.41.000000_".
    _UPLOAD_PREFIX: ClassVar[re.Pattern[str]] = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{2}\.\d{2}\.\d{2}\.\d+_")

    # --- rules of one file ---

    @staticmethod
    def name_without_prefix(name: str) -> str:
        return Repetitions._UPLOAD_PREFIX.sub("", name)

    @staticmethod
    def is_no_piaa(record: FileRecord) -> bool:
        return NO_PIAA_MARK in record.nombre

    @staticmethod
    def _counts(record: FileRecord) -> bool:
        """Files that enter the counts: complete ones with an assigned code."""
        return (
            record.completo
            and record.anio is not None
            and record.codigo is not None
            and record.codigo != UNASSIGNED_CODE
        )

    @staticmethod
    def _has_content(record: FileRecord) -> bool:
        return record.sha256 is not None and record.bytes > 0

    # --- comparison between uploads ---

    @staticmethod
    def _exact_copy(previous: FileRecord, current: FileRecord) -> bool:
        return Repetitions._has_content(current) and previous.sha256 == current.sha256 and previous.bytes > 0

    @staticmethod
    def _no_piaa(previous: FileRecord, current: FileRecord) -> bool:
        return Repetitions.is_no_piaa(previous) or Repetitions.is_no_piaa(current)

    @staticmethod
    def _other_format(previous: FileRecord, current: FileRecord) -> bool:
        return previous.tipo != current.tipo

    @staticmethod
    def _same_name(previous: FileRecord, current: FileRecord) -> bool:
        name = Repetitions.name_without_prefix
        return name(previous.nombre).casefold() == name(current.nombre).casefold()

    # Checked in the order of Reason: the first one that holds wins (OTHER_NAME when none does). A new reason is its
    # value in Reason and its rule here.
    _RULES: ClassVar[dict[Reason, Callable[[FileRecord, FileRecord], bool]]] = {
        Reason.EXACT_COPY: _exact_copy,
        Reason.NO_PIAA: _no_piaa,
        Reason.OTHER_FORMAT: _other_format,
        Reason.SAME_NAME: _same_name,
    }

    @staticmethod
    def reason(previous: FileRecord, current: FileRecord) -> Reason:
        return next((r for r, holds in Repetitions._RULES.items() if holds(previous, current)), Reason.OTHER_NAME)

    @staticmethod
    def _seconds(previous: FileRecord, current: FileRecord) -> float:
        return (
            datetime.fromisoformat(current.modificado) - datetime.fromisoformat(previous.modificado)
        ).total_seconds()

    @staticmethod
    def interval(seconds: float) -> int:
        """Index in INTERVALS."""
        return next(i for i, (limit, _) in enumerate(Repetitions.INTERVALS) if seconds < limit)

    @staticmethod
    def _time(seconds: list[float]) -> NumericSummary | None:
        """None if there are no cases."""
        return numeric_summary(seconds) if seconds else None

    @staticmethod
    def _between_uploads(repeated: Iterable[RepeatedCode]) -> list[float]:
        return [u.seconds for c in repeated for u in c.uploads if u.seconds is not None]

    @staticmethod
    def _first_last(code: RepeatedCode) -> float:
        return Repetitions._seconds(code.uploads[0].record, code.uploads[-1].record)

    # --- grouping ---

    @staticmethod
    def _by_code_year(records: Iterable[FileRecord]) -> dict[CodeYearKey, list[FileRecord]]:
        groups: defaultdict[CodeYearKey, list[FileRecord]] = defaultdict(list)
        for record in records:
            if Repetitions._counts(record) and record.anio is not None and record.codigo is not None:
                groups[(record.anio, record.codigo)].append(record)
        return groups

    @staticmethod
    def group(records: Iterable[FileRecord]) -> list[RepeatedCode]:
        """Codes with two or more files in a year, by year and code; each one in upload order."""
        repeated = []
        for (year, code), members in sorted(Repetitions._by_code_year(records).items()):
            if len(members) < 2:
                continue
            members.sort(key=Duplicates.newness_key)
            uploads = [RepeatedUpload(members[0], None, None)]
            uploads += [
                RepeatedUpload(b, Repetitions.reason(a, b), Repetitions._seconds(a, b)) for a, b in pairwise(members)
            ]
            repeated.append(RepeatedCode(year, code, tuple(uploads)))
        return repeated

    # --- report ---

    @staticmethod
    def _row(year: int, records: list[FileRecord], repeated: list[RepeatedCode]) -> RepeatedYearRow:
        of_year = [r for r in records if Repetitions._counts(r)]
        hashes = Counter(r.sha256 for r in of_year if Repetitions._has_content(r))
        without_template = Counter(
            r.sha256 for r in of_year if Repetitions._has_content(r) and not Repetitions.is_no_piaa(r)
        )
        by_code = Counter(r.codigo for r in of_year)
        reasons: Counter[Reason] = Counter()
        intervals: Counter[int] = Counter()
        by_month: Counter[int] = Counter()
        for c in repeated:
            for u in c.uploads[1:]:
                if u.reason is not None and u.seconds is not None:
                    reasons[u.reason] += 1
                    intervals[Repetitions.interval(u.seconds)] += 1
                if u.record.mes_num:
                    by_month[u.record.mes_num] += 1
        counts = Counter(min(len(c.uploads), Repetitions.MAX_COUNT) for c in repeated)
        return RepeatedYearRow(
            anio=year,
            archivos=len(of_year),
            codigos=len(by_code),
            codigos_repetidos=len(repeated),
            archivos_en_repetidos=sum(len(c.uploads) for c in repeated),
            sobrantes_codigo=len(of_year) - len(by_code),
            sobrantes_hash=hashes.total() - len(hashes),
            sobrantes_hash_sin_plantilla=without_template.total() - len(without_template),
            max_por_codigo=max(by_code.values(), default=0),
            sin_piaa=sum(1 for r in of_year if Repetitions.is_no_piaa(r)),
            codigo_sin_asignar=sum(1 for r in records if r.completo and r.codigo == UNASSIGNED_CODE),
            por_cantidad=[counts[n] for n in range(2, Repetitions.MAX_COUNT + 1)],
            motivos=[reasons[m] for m in Reason],
            intervalos=[intervals[i] for i in range(len(Repetitions.INTERVALS))],
            sobrantes_por_mes=[by_month[m] for m in range(1, 13)],
            tiempo_entre_subidas=Repetitions._time(Repetitions._between_uploads(repeated)),
            tiempo_primera_ultima=Repetitions._time([Repetitions._first_last(c) for c in repeated]),
        )

    @staticmethod
    def _top_entry(code: RepeatedCode) -> RepeatedCodeReport:
        records = [u.record for u in code.uploads]
        reasons = Counter(u.reason for u in code.uploads)
        return RepeatedCodeReport(
            anio=code.year,
            codigo=code.code,
            archivos=len(records),
            contenidos=len({r.sha256 for r in records}),
            primero=records[0].modificado,
            ultimo=records[-1].modificado,
            mediana_entre_subidas=statistics.median(Repetitions._between_uploads([code])),
            motivos=[reasons[m] for m in Reason],
            nombres=sorted({Repetitions.name_without_prefix(r.nombre) for r in records}),
        )

    @staticmethod
    def build_report(records: list[FileRecord], repeated: list[RepeatedCode]) -> RepeatedReport:
        by_year: defaultdict[int, list[FileRecord]] = defaultdict(list)
        for record in records:
            if record.completo and record.anio is not None:
                by_year[record.anio].append(record)
        repeated_by_year: defaultdict[int, list[RepeatedCode]] = defaultdict(list)
        for c in repeated:
            repeated_by_year[c.year].append(c)

        years_by_code: defaultdict[str, set[int]] = defaultdict(set)
        for year, code in Repetitions._by_code_year(records):
            years_by_code[code].add(year)
        top = sorted(repeated, key=lambda c: (-len(c.uploads), c.year, c.code))[:TOP_REPEATED]
        return RepeatedReport(
            codigo_sin_asignar=UNASSIGNED_CODE,
            marca_sin_piaa=NO_PIAA_MARK,
            cantidades=[*map(str, range(2, Repetitions.MAX_COUNT)), f"{Repetitions.MAX_COUNT}+"],
            motivos=[m.value for m in Reason],
            intervalos=[label for _, label in Repetitions.INTERVALS],
            filas=[Repetitions._row(y, by_year[y], repeated_by_year[y]) for y in sorted(by_year)],
            anios_por_codigo=sorted(Counter(len(y) for y in years_by_code.values()).items()),
            principales=[Repetitions._top_entry(c) for c in top],
            tiempo_entre_subidas=Repetitions._time(Repetitions._between_uploads(repeated)),
            tiempo_por_motivo=[
                Repetitions._time(
                    [u.seconds for c in repeated for u in c.uploads if u.reason is m and u.seconds is not None]
                )
                for m in Reason
            ],
        )
