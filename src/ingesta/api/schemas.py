"""API response bodies (the ones that aren't already an ingesta.models model). The FIELD names are response
keys (memory columns and /stats keys): they stay in Spanish."""

from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import ConfigDict
from pydantic.dataclasses import dataclass as pydantic_dataclass

from ingesta.models import (
    DuplicatesSummary,
    FileRecord,
    NumericSummary,
    RepeatedCodeReport,
    RepeatedYearRow,
    SourceCheck,
    SourceKind,
)


@dataclass(frozen=True)
class Error:
    detalle: str


@dataclass(frozen=True)
class HealthStatus:
    estado: str
    version: str
    memoria: str  # memory URL, without password


@dataclass(frozen=True)
class ChunkableFiles:
    """A page of GET /data."""

    reorganizado: str | None  # end (ISO) of the last finished organize run; None if none ever finished
    pagina: int
    por_pagina: int
    total: int  # files that meet the filters, across all pages
    paginas: int
    archivos: list[FileRecord]


# --- sections of GET /stats (parts of ReportData, with the same field names) ---


@dataclass(frozen=True)
class BasicSummary:
    """The report's «Estadísticas básicas»."""

    archivos: int
    bytes: int
    total_codigos: int
    total_tipos: int  # before grouping into "otros"
    incompletos: int  # without complete structure (outside the date charts)
    bytes_incompletos: int


@dataclass(frozen=True)
class TypesReport:
    total_tipos: int
    tipos: list[str]  # main ones, and "otros" at the end if needed
    otros: dict[str, int]  # types grouped in "otros" -> files
    resumen_por_tipo: dict[str, NumericSummary]  # sizes in bytes


@dataclass(frozen=True)
class TypeReport:
    """Everything the report says about one type."""

    tipo: str
    agrupa: list[str]  # if it is "otros", the types it groups
    resumen: NumericSummary  # sizes in bytes
    anios: list[int]
    archivos_por_anio: list[int]  # aligned with anios (complete ones only)
    bytes_por_anio: list[int]  # aligned with anios (complete ones only)
    copias: int  # leftover copies by content
    vacios: int  # 0 B
    casi_vacios: int


@dataclass(frozen=True)
class DuplicatedCodes:
    """«Códigos duplicados»: codes with more than one file (without empty files or copies by content)."""

    total: int  # duplicated codes, ignoring the limit
    codigos: list[tuple[str, int]]  # (code, files), from most to fewest files


@dataclass(frozen=True)
class RepeatedYear:
    """«PIAA repetidos por año» of a single year; the lists of `fila` are aligned with cantidades/motivos/intervalos."""

    fila: RepeatedYearRow
    cantidades: list[str]
    motivos: list[str]
    intervalos: list[str]
    principales: list[RepeatedCodeReport]  # the ones of that year among those with the most files


# --- ingestion from the API (feature 030) ---


class IngestionState(StrEnum):
    RUNNING = "en_curso"
    FINISHED = "terminada"
    FAILED = "fallida"


@pydantic_dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class SourceRequest:
    """Where to ingest from (request keys in English, like the query parameters): always the server's base folder
    (data/base/) or, later, an external SQL database. There is no path: the API never reads another folder."""

    kind: SourceKind = SourceKind.FOLDER


@pydantic_dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class NewIngestion:
    """Body of POST /runs. The source is never moved nor deleted: the API only copies."""

    source: SourceRequest = field(default_factory=SourceRequest)
    simulate: bool = False  # only check and say what it would do


@dataclass(frozen=True)
class FileFailureItem:
    origen: str
    error: str
    destino: str | None


@dataclass(frozen=True)
class PlannedCopy:
    origen: str  # relative path in the source
    destino: str  # provisional folder/name in ingesta/ (the final category depends on the hash)


@dataclass(frozen=True)
class IngestionSimulation:
    """POST /runs with simulate: the check and what would be copied and relocated, without touching anything."""

    revision: SourceCheck
    copiaria: int
    primeros: list[PlannedCopy]  # up to MAX_PLANNED
    reubicaria: int  # files already in ingesta/ that would change folder
    carpetas: dict[str, int]  # files per main category, as the memory is now


@dataclass(frozen=True)
class IngestionProgress:
    copiados: int
    total: int  # new files of the run


@dataclass(frozen=True)
class IngestionSummary:
    copiados: int
    errores: int
    hashes_rellenados: int
    metadata_rellenada: int
    reubicados: int
    categorias_agregadas: int
    categorias_quitadas: int
    principal_cambiada: int
    carpetas: dict[str, int]  # files per main category (folder)
    con_cada_categoria: dict[str, int]
    duplicados: DuplicatesSummary
    duplicados_nuevos: int  # files of this run whose content was already in the memory


@dataclass(frozen=True)
class IngestionRun:
    """An ingestion started from the API: GET /runs/{id}."""

    id: str
    estado: IngestionState
    inicio: str
    fin: str | None
    revision: SourceCheck
    progreso: IngestionProgress
    resultado: IngestionSummary | None = None
    errores: list[FileFailureItem] = field(default_factory=list)  # up to MAX_FAILURES; the count is in `resultado`
    error: str | None = None  # why the whole run failed (memory down...)
