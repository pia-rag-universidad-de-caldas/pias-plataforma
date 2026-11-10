"""Data of the statistics (GET /stats). They are serialized to JSON with dataclasses.asdict, so the FIELD names are
the keys of the API responses: they stay in Spanish."""

from dataclasses import dataclass

from .results import DuplicatesSummary


@dataclass(frozen=True)
class NumericSummary:
    """Descriptive statistics of a group of values: sizes (bytes) per type or times (seconds) between uploads.
    Inclusive quartiles; whiskers and outliers with the 1.5×IQR rule."""

    casos: int
    total: float
    min: float
    q1: float
    mediana: float
    media: float
    q3: float
    p90: float
    max: float
    desviacion: float  # population standard deviation
    bigote_inf: float  # lowest value within 1.5×IQR
    bigote_sup: float  # highest value within 1.5×IQR
    atipicos: int  # outside the whiskers


@dataclass(frozen=True)
class YearRow:
    """One row of the yearly growth table."""

    anio: int
    archivos: int
    bytes: int
    meses_activos: int  # months with at least one file
    parcial: bool  # fewer than 12 months with data: the total is not comparable
    promedio_mes: float  # files per month with data
    crecimiento: float | None  # % of the total against the previous year; None for the first one
    crecimiento_mes: float | None  # % of the monthly average against the previous year


@dataclass(frozen=True)
class YearsComparison:
    """Report sections «Por año» and «Comparación entre años» (same fields as ReportData), for the API."""

    anios: list[int]
    tipos: list[str]
    filas_anios: list[YearRow]
    archivos_anio_tipo: dict[int, list[int]]  # year -> files per type
    bytes_tipo_anio: dict[str, list[int]]  # type -> bytes per year
    archivos_anio_mes: dict[int, list[int]]  # year -> files per month


@dataclass(frozen=True)
class YearComparison:
    """«Por año» and «Comparación entre años» of a single year."""

    fila: YearRow
    tipos: list[str]
    archivos_por_tipo: list[int]  # aligned with tipos
    bytes_por_tipo: list[int]  # aligned with tipos
    archivos_por_mes: list[int]  # from January (0) to December (11)


@dataclass(frozen=True)
class DuplicateGroupReport:
    """A duplicate group as shown in the report table."""

    sha256: str
    bytes: int  # size of each file in the group
    tipo: str  # type of the original, already grouped in "otros" if needed
    rutas: list[str]  # targets in ingesta/; the first one is the original
    anios: list[int]  # years present in the group (without the unknown ones)


@dataclass(frozen=True)
class DuplicatesReport:
    resumen: DuplicatesSummary
    grupos_multi_codigo: int  # groups whose files are in more than one code
    sin_hash: int
    copias_por_tipo: list[int]  # aligned with ReportData.tipos
    copias_por_anio: list[tuple[str, int]]  # (year or "sin año", copies)
    principales: list[DuplicateGroupReport]  # the ones with the most recoverable space


@dataclass(frozen=True)
class SmallFile:
    destino: str  # relative path in ingesta/
    tipo: str
    bytes: int


@dataclass(frozen=True)
class EmptyFilesReport:
    """Empty (0 B) or almost empty files (from 1 B to less than `umbral`)."""

    umbral: int  # bytes
    carpeta: str  # where they are inside ingesta/
    vacios: int
    casi_vacios: int
    vacios_por_tipo: list[int]  # aligned with ReportData.tipos
    casi_vacios_por_tipo: list[int]  # aligned with ReportData.tipos
    menores: list[SmallFile]  # the smallest ones, up to TOP_EMPTY


@dataclass(frozen=True)
class CleanupReport:
    """Funnel of the ingesta classification (domain.classification): what leaves at each step and what remains."""

    total: int
    vacios: int
    sin_vacios: int
    extranios: int
    solo_soportados: int
    hash_duplicados: int
    sin_duplicados: int
    codigos_duplicados: int
    incompletos: int
    aptos_chunking: int  # vigentes/ folder


@dataclass(frozen=True)
class RepeatedYearRow:
    """Repeated PIAA of a year. The counts exclude the unassigned code (see `codigo_sin_asignar`)."""

    anio: int
    archivos: int
    codigos: int
    codigos_repetidos: int  # with two or more files in the year
    archivos_en_repetidos: int
    sobrantes_codigo: int  # archivos - codigos
    sobrantes_hash: int  # files that repeat the content of another one of the same year
    sobrantes_hash_sin_plantilla: int  # the same without counting the SIN_PIAA template
    max_por_codigo: int
    sin_piaa: int  # files with the SIN_PIAA template
    codigo_sin_asignar: int  # files with the unassigned code (outside the counts)
    por_cantidad: list[int]  # aligned with RepeatedReport.cantidades
    motivos: list[int]  # aligned with RepeatedReport.motivos
    intervalos: list[int]  # aligned with RepeatedReport.intervalos
    sobrantes_por_mes: list[int]  # from January (0) to December (11)
    tiempo_entre_subidas: NumericSummary | None  # each file against the previous one of its code; None without repeats
    tiempo_primera_ultima: NumericSummary | None  # from the first to the last upload of each repeated code


@dataclass(frozen=True)
class RepeatedCodeReport:
    anio: int
    codigo: str
    archivos: int
    contenidos: int  # distinct sha256
    primero: str  # modificado of the first upload (ISO)
    ultimo: str  # modificado of the last upload (ISO)
    mediana_entre_subidas: float  # seconds
    motivos: list[int]  # aligned with RepeatedReport.motivos
    nombres: list[str]  # distinct names, without the upload date prefix


@dataclass(frozen=True)
class RepeatedReport:
    """PIAA (code within a year) with two or more files in the same year."""

    codigo_sin_asignar: str
    marca_sin_piaa: str
    cantidades: list[str]  # "2", "3", ..., "6+"
    motivos: list[str]
    intervalos: list[str]
    filas: list[RepeatedYearRow]
    anios_por_codigo: list[tuple[int, int]]  # (distinct years it appears in, codes)
    principales: list[RepeatedCodeReport]  # the ones with the most files, up to TOP_REPEATED
    tiempo_entre_subidas: NumericSummary | None  # all years
    tiempo_por_motivo: list[NumericSummary | None]  # aligned with motivos; all years


@dataclass(frozen=True)
class ReportData:
    """Everything the report shows.

    The per-type lists are aligned with `tipos` and the per-month ones go from January (0) to December (11).
    """

    archivos: int
    bytes: int
    total_codigos: int
    total_tipos: int  # distinct types before grouping into "otros"
    tipos: list[str]  # main ones, and "otros" at the end if needed
    otros: dict[str, int]  # types grouped in "otros" -> number of files
    resumen_por_tipo: dict[str, NumericSummary]
    codigos_principales: list[tuple[str, int]]  # (code, files)
    anios: list[int]  # only files with complete structure
    archivos_anio_tipo: dict[int, list[int]]  # year -> files per type
    bytes_tipo_anio: dict[str, list[int]]  # type -> bytes per year
    archivos_anio_mes: dict[int, list[int]]  # year -> files per month
    filas_anios: list[YearRow]
    duplicados: DuplicatesReport
    vacios: EmptyFilesReport
    limpieza: CleanupReport
    incompletos: int  # files without complete structure (outside the date charts)
    bytes_incompletos: int
    repetidos: RepeatedReport
