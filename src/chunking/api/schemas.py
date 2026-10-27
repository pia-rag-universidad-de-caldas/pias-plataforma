"""The bodies every part of the chunking API shares (new code: keys in English, like data); those of runs and
experiments live in runs/schemas.py and experiments/schemas.py. The responses that are already a chunking.models model
(ChunkingRun, DocumentPage, DocumentChunks, ProcessedDocument) are used as they are."""

from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import Field

type ServiceState = Literal["ok", "unavailable"]


@dataclass(frozen=True)
class HealthStatus:
    status: Literal["ok", "degraded"]  # "ok" if Docling is installed and ingesta and data answer
    version: str
    docling: Literal["installed", "missing"]
    docling_version: str | None
    ingesta: ServiceState
    data: ServiceState


type Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]  # lowercase hex, as ingesta stores it
