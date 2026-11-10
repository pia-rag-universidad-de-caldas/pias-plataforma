"""The chunkable files in data (feature 042): each one is published as a RAW node, so that the other modules read it
from there and never from ingesta. What the domain asks of data (RawStore) and what a publication did.

The fields of RawSummary and RawPreview are keys of the API's JSON: they stay in Spanish.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from .entities import FileRecord


class RawStoreError(Exception):
    """data doesn't answer (or answers something unexpected): nothing more is published in this run."""


class RawFileRejected(Exception):
    """data refused one file (too big, outside its schema...): only that one fails."""


class RawStore(Protocol):
    def published(self) -> Mapping[str, bool]:
        """The sha256 of every RAW in data and whether it is still current (`vigente`), without the content."""
        ...

    def publish(self, record: FileRecord, content: bytes, at: str) -> None:
        """Writes (merge) the RAW of `record` with its content, as current."""
        ...

    def retire(self, sha256s: Sequence[str]) -> None:
        """Marks those RAW as no longer current; they are never deleted (their JSON and chunks may still be used)."""
        ...


@dataclass(frozen=True)
class RawPlan:
    """What a publication would do: the chunkable files data doesn't have (or has as no longer current), how many it
    already has and the RAW whose file stopped being chunkable."""

    upload: list[FileRecord]
    already: int
    retire: list[str]


@dataclass(frozen=True)
class RawFailure:
    sha256: str
    origen: str
    error: str


@dataclass(frozen=True)
class RawSummary:
    """What the end of an ingestion published in data (GET /runs/{id}, `resultado.en_data`)."""

    subidos: int = 0
    ya_estaban: int = 0
    retirados: int = 0
    fallidos: int = 0
    errores: list[RawFailure] = field(default_factory=list)  # up to MAX_RAW_FAILURES; all of them count in fallidos
    aviso: str | None = None  # why it published nothing (or stopped): data doesn't answer, the server has no URL...


@dataclass(frozen=True)
class RawPreview:
    """What a simulation would publish, as data and the memory are now."""

    subiria: int = 0
    ya_estan: int = 0
    retiraria: int = 0
    aviso: str | None = None
