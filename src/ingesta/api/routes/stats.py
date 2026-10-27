"""GET /stats: the statistics of the memory, whole or by section, and the detail of a year, a type or a PIAA-year.

Every request rebuilds the statistics from the memory (Statistics.build); each section is a part of the whole with
the same field names.
"""

from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from ingesta.api.dependencies import Memory
from ingesta.api.schemas import (
    BasicSummary,
    DuplicatedCodes,
    Error,
    RepeatedYear,
    TypeReport,
    TypesReport,
)
from ingesta.domain import Duplicates, Naming, Repetitions, Statistics
from ingesta.models import (
    CleanupReport,
    DuplicatesReport,
    EmptyFilesReport,
    RepeatedReport,
    ReportData,
    YearComparison,
    YearsComparison,
)
from ingesta.repository import DbFileRepository

router = APIRouter(prefix="/stats", tags=["stats"])

_NO_MEMORY = "the memory could not be opened"
_NO_YEAR = "no files with complete structure in that year"


def _statistics(memory: Memory) -> ReportData:
    records = DbFileRepository(memory).all()
    return Statistics.build(records, Duplicates.group(records), Repetitions.group(records))


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail)


@router.get("", responses={503: {"model": Error, "description": _NO_MEMORY}})
def everything(memory: Memory) -> ReportData:
    """Every section of the statistics at once."""
    return _statistics(memory)


@router.get("/summary", responses={503: {"model": Error, "description": _NO_MEMORY}})
def summary(memory: Memory) -> BasicSummary:
    """Basic statistics: totals of files, bytes, codes and types."""
    s = _statistics(memory)
    return BasicSummary(s.archivos, s.bytes, s.total_codigos, s.total_tipos, s.incompletos, s.bytes_incompletos)


@router.get("/types", responses={503: {"model": Error, "description": _NO_MEMORY}})
def types(memory: Memory) -> TypesReport:
    """The report's file types and the size distribution of each one."""
    s = _statistics(memory)
    return TypesReport(s.total_tipos, s.tipos, s.otros, s.resumen_por_tipo)


@router.get(
    "/types/{file_type}",
    responses={
        404: {"model": Error, "description": "type that is not in the report"},
        503: {"model": Error, "description": _NO_MEMORY},
    },
)
def file_type(memory: Memory, file_type: str) -> TypeReport:
    """Everything the report says about one type: sizes, files and bytes per year, copies and empty files. The
    rare types are inside `otros`."""
    s = _statistics(memory)
    name = Naming.file_type(f"x.{file_type.lstrip('.')}")
    if name not in s.tipos:
        in_others = " (it is grouped in otros: /stats/types/otros)" if name in s.otros else ""
        raise _not_found(f"the type {name} is not one of the report's types{in_others}")
    i = s.tipos.index(name)
    return TypeReport(
        tipo=name,
        agrupa=sorted(s.otros) if name == Statistics.OTHERS else [],
        resumen=s.resumen_por_tipo[name],
        anios=s.anios,
        archivos_por_anio=[s.archivos_anio_tipo[y][i] for y in s.anios],
        bytes_por_anio=s.bytes_tipo_anio[name],
        copias=s.duplicados.copias_por_tipo[i],
        vacios=s.vacios.vacios_por_tipo[i],
        casi_vacios=s.vacios.casi_vacios_por_tipo[i],
    )


@router.get("/years", responses={503: {"model": Error, "description": _NO_MEMORY}})
def years(memory: Memory) -> YearsComparison:
    """By year and comparison between years (only files with complete structure)."""
    return Statistics.year_comparison(DbFileRepository(memory).all())


@router.get(
    "/years/{year}",
    responses={404: {"model": Error, "description": _NO_YEAR}, 503: {"model": Error, "description": _NO_MEMORY}},
)
def year(memory: Memory, year: int) -> YearComparison:
    """One year: files and bytes per type, files per month and growth against the previous year."""
    comparison = Statistics.year(DbFileRepository(memory).all(), year)
    if comparison is None:
        raise _not_found(f"{_NO_YEAR}: {year}")
    return comparison


@router.get("/duplicates", responses={503: {"model": Error, "description": _NO_MEMORY}})
def duplicates(memory: Memory, limit: Annotated[int | None, Query(ge=1)] = None) -> DuplicatesReport:
    """Duplicates by content (same sha256): summary, copies per type and year and the groups that take the most
    space; `limit` returns only the first groups (each one lists all its paths)."""
    d = _statistics(memory).duplicados
    return replace(d, principales=d.principales[:limit])


@router.get("/empty", responses={503: {"model": Error, "description": _NO_MEMORY}})
def empty(memory: Memory) -> EmptyFilesReport:
    """Empty (0 B) or almost empty files, per type, and the smallest ones."""
    return _statistics(memory).vacios


@router.get("/codes", responses={503: {"model": Error, "description": _NO_MEMORY}})
def codes(memory: Memory, limit: Annotated[int | None, Query(ge=1)] = None) -> DuplicatedCodes:
    """Duplicated codes, from most to fewest files; `limit` returns only the first ones."""
    main_codes = _statistics(memory).codigos_principales
    return DuplicatedCodes(total=len(main_codes), codigos=main_codes[:limit])


@router.get("/repeated", responses={503: {"model": Error, "description": _NO_MEMORY}})
def repeated(memory: Memory) -> RepeatedReport:
    """Repeated PIAA per year: a code with two or more files in the same year."""
    return _statistics(memory).repetidos


@router.get(
    "/repeated/{year}",
    responses={404: {"model": Error, "description": _NO_YEAR}, 503: {"model": Error, "description": _NO_MEMORY}},
)
def repeated_year(memory: Memory, year: int) -> RepeatedYear:
    """Repeated PIAA of one year, with that year's codes that have the most files."""
    r = _statistics(memory).repetidos
    row = next((f for f in r.filas if f.anio == year), None)
    if row is None:
        raise _not_found(f"{_NO_YEAR}: {year}")
    top = [c for c in r.principales if c.anio == year]
    return RepeatedYear(row, r.cantidades, r.motivos, r.intervalos, top)


@router.get("/cleanup", responses={503: {"model": Error, "description": _NO_MEMORY}})
def cleanup(memory: Memory) -> CleanupReport:
    """Classification funnel: what leaves at each step and what remains ready for chunking."""
    return _statistics(memory).limpieza
