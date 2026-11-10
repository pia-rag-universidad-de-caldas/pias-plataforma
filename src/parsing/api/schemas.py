"""Bodies of the parsing API (new code: keys in English, like data and chunking). The responses that already are a
parsing.models model (ParsingRun) are used as they are."""

from dataclasses import dataclass, field
from typing import Annotated, Literal

from pydantic import ConfigDict, Field

STRICT = ConfigDict(extra="forbid")  # an unknown key is a 422, never ignored

type Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]  # lowercase hex, as ingesta stores it
type ServiceState = Literal["ok", "unavailable"]


@dataclass(frozen=True)
class NewRun:
    """Body of POST /runs: these sha256 (the RAW of data), repeated ones once; without them, every current RAW still to
    parse (with `redo`, every current one), decided when the run is queued."""

    __pydantic_config__ = STRICT

    sha256s: list[Sha256] = field(default_factory=list)
    redo: bool = False  # parse again even those already parsed with the same fingerprint
    simulate: bool = False  # only say what it would do: nothing is converted nor written


@dataclass(frozen=True)
class ConfigView:
    """GET /config: the fixed configuration (read only) and the fingerprint it gives with this Docling."""

    version: int
    docling: str | None
    fingerprint: str | None  # None without Docling
    config: dict[str, object]


@dataclass(frozen=True)
class HealthStatus:
    status: Literal["ok", "degraded"]  # "ok" if Docling and the OCR engine are installed and data answers
    version: str
    docling: Literal["installed", "missing"]
    docling_version: str | None
    ocr: Literal["installed", "missing"]
    libreoffice: Literal["installed", "missing"]  # only for .doc: its absence doesn't degrade the module
    data: ServiceState
