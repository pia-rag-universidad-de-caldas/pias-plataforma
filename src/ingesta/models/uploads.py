"""Uploads through the API (feature 049): a file as it arrives and what became of it. The FIELDS of UploadResult and
the VALUES of UploadState are JSON keys and values of POST /uploads: they stay in Spanish."""

from dataclasses import dataclass
from enum import StrEnum


class UploadState(StrEnum):
    SAVED = "guardado"  # written in base/: the next ingestion copies it
    EXISTS = "ya_existe"  # the same content (sha256) is already in the corpus or was already uploaded
    REJECTED = "rechazado"  # not saved: `motivo` says why


@dataclass(frozen=True)
class IncomingFile:
    """One uploaded file, as the client sent it."""

    name: str
    content: bytes


@dataclass(frozen=True)
class UploadResult:
    nombre: str  # the name it was sent with
    estado: UploadState
    sha256: str
    ruta: str | None = None  # relative to base/: where it was saved or where its content already is
    motivo: str | None = None  # only when rejected
