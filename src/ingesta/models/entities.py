"""Rows of the memory tables: one dataclass per table and one field per column, with the same name (see
tables/). The adapter stores and returns them as they are.

The FIELD names are the column names of the existing memory (data/ingesta/.memoria.sqlite3), so they stay in
Spanish: renaming one means migrating the memory."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FileRecord:
    """Table `archivos`: an already processed file."""

    origen: str  # relative path inside base/
    destino: str  # relative path inside ingesta/
    anio: int | None  # None for an incomplete format if it could not be known
    mes: str | None
    mes_num: int | None
    semana: str | None
    codigo: str | None
    nombre: str  # original file name
    tipo: str  # normalized extension (target folder)
    bytes: int
    modificado: str  # mtime of the original file (ISO)
    procesado_en: str  # ISO
    accion: str  # copiado | movido
    sha256: str | None
    completo: bool  # False if it did not follow anio/mes/semana/codigo/archivo
    # Metadata of the original when it was ingested (None in old records until they are filled in).
    creado: str | None = None  # ISO; None if the system does not provide the creation date (Linux)
    cambiado: str | None = None  # last metadata change (ctime, ISO)
    accedido: str | None = None  # last access (atime, ISO)
    permisos: str | None = None  # octal, "644"
    mime: str | None = None  # from the extension; None if unknown


@dataclass(frozen=True)
class Run:
    """Table `ejecuciones`: one run of `organize`."""

    inicio: str  # ISO
    accion: str  # copiado | movido
    fin: str | None = None  # None while it runs (or if it was interrupted)
    nuevos: int = 0
    omitidos: int = 0
    errores: int = 0
    id: int | None = None  # assigned by the database on insert


@dataclass(frozen=True)
class CategoryDefinition:
    """Table `categorias` (catalog): one row per Category value."""

    nombre: str  # Category value
    carpeta: str  # ingesta/ folder when it is the main one
    prioridad: int  # 1 = highest priority
    descripcion: str


@dataclass(frozen=True)
class FileCategory:
    """Table `archivos_categorias`: one category of a file (many-to-many relationship)."""

    origen: str  # archivos.origen
    categoria: str  # categorias.nombre
    principal: bool  # the one that decides the folder; exactly one per file
