"""What is stored in the graph (feature 042): one TypedDict per shape, used by who writes it (domain/graph.py) and by
who reads it (adapters), so that a misspelled key is a mypy error. The keys are Neo4j property names: Spanish."""

from typing import TypedDict


class RawProperties(TypedDict, total=False):
    """What parsing reads of a RAW (ingesta writes the file's ones; parsing, the parse state)."""

    nombre: str
    tipo: str
    codigo: str | None
    vigente: bool
    contenido: str  # base64
    estado_parseo: str | None
    fingerprint_parseo: str | None


class RawParseProperties(TypedDict, total=False):
    """What parsing writes on a RAW (merge: ingesta's properties stay)."""

    parseado: bool
    estado_parseo: str
    parseado_en: str
    fingerprint_parseo: str
    error_parseo: str | None


class ParsedJsonProperties(TypedDict):
    """A JSON node: the parsed document. The file's metadata stays in its RAW."""

    sha256: str
    estado: str
    error: str | None
    fingerprint_parseo: str
    docling: str
    parseado_en: str
    duracion_parseo: float
    paginas_totales: int
    paginas_procesadas: int
    paginas_pendientes: list[int]
    paginas_sin_texto: list[int]
    paginas_ocr: list[int]
    documento: str  # the DoclingDocument (export_to_dict) as JSON, gzip and base64
    documento_bytes: int  # its size as JSON, before compressing


class RunProperties(TypedDict):
    """A CORRIDA_PARSEO node: a run, as GET /runs answers it (`detalle`, JSON)."""

    estado: str
    inicio: str
    detalle: str
