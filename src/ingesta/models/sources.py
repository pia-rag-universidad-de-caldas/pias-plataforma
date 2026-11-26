"""Where an ingestion reads its files from (feature 030) and what the check of that source found.

Today a source is a folder; an external SQL database will be another read-only FileAdapter (it lists the files and
hands their content), so the domain only ever sees a FileAdapter. The FIELD names and the VALUES of the codes and
levels are API JSON: they stay in Spanish.
"""

from dataclasses import dataclass, field
from enum import StrEnum


class SourceKind(StrEnum):
    FOLDER = "folder"
    SQL = "sql"  # an external SQL database: not available yet


class IssueLevel(StrEnum):
    WARNING = "advertencia"  # the ingestion can run
    ERROR = "error"  # the ingestion is refused


class IssueCode(StrEnum):
    NOT_FOUND = "no_encontrada"
    NOT_A_FOLDER = "no_es_carpeta"
    UNREADABLE = "ilegible"
    OVERLAPS_INGEST = "solapa_ingesta"  # it is the ingesta folder, is inside it or contains it
    EMPTY = "vacia"
    ONLY_HIDDEN = "solo_ocultos"
    NO_STRUCTURE = "sin_estructura"  # no file follows <year>/<month>/<week>/<code>/<file>
    SOME_INCOMPLETE = "estructura_incompleta"  # some files don't: they go to formato_incompleto/
    NOTHING_NEW = "nada_nuevo"


class SourceUnavailable(Exception):
    """The requested kind of source can't be opened (e.g. `sql`, not implemented yet)."""


@dataclass(frozen=True)
class SourceIssue:
    codigo: IssueCode
    nivel: IssueLevel
    mensaje: str


@dataclass(frozen=True)
class SourceCheck:
    """What a source has, compared with the memory, and why it can't be ingested (if so)."""

    tipo: SourceKind
    ubicacion: str  # absolute path (or visible URL) of the source
    encontrada: bool
    estado: str = "ok"  # the worst level of `problemas` ("error", "advertencia") or "ok": see SourceCheck.state
    archivos: int = 0  # visible files (hidden ones not counted)
    ocultos: int = 0
    completos: int = 0
    incompletos: int = 0
    nuevos: int = 0  # not in the memory yet
    ya_en_memoria: int = 0
    tipos: dict[str, int] = field(default_factory=dict)  # visible files per extension
    ejemplos_incompletos: list[str] = field(default_factory=list)
    problemas: list[SourceIssue] = field(default_factory=list)

    @staticmethod
    def state(problems: list[SourceIssue]) -> str:
        """The worst level: "error", "advertencia" or "ok"."""
        levels = {p.nivel for p in problems}
        if IssueLevel.ERROR in levels:
            return IssueLevel.ERROR.value
        return IssueLevel.WARNING.value if levels else "ok"

    @property
    def usable(self) -> bool:
        return self.estado != IssueLevel.ERROR.value
