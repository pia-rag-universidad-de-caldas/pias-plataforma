"""The bodies every part of the chunking API shares (keys in English, like data); those of experiments, the
configuration and runs live in their packages. A response that is already a chunking.models model (ChunkingRun) is used
as it is."""

from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from chunking.config import MAX_TOKENS_RANGE
from chunking.models import DoclingChunker, RequestedChunking

type ServiceState = Literal["ok", "unavailable"]
STRICT = ConfigDict(extra="forbid")  # an unknown key is a 422: never silently ignored


@dataclass(frozen=True)
class HealthStatus:
    status: Literal["ok", "degraded"]  # "ok" if docling-core is installed and data answers
    version: str
    docling_core: Literal["installed", "missing"]
    docling_core_version: str | None
    data: ServiceState


type Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]  # lowercase hex, as ingesta stores it


@dataclass(frozen=True)
class ChunkingBody:
    """The configurable part; what is left out takes CHUNKING_DEFAULT. max_tokens and merge_peers only with hybrid."""

    __pydantic_config__ = STRICT

    chunker: DoclingChunker | None = None  # hybrid (default), hierarchical or page
    tokenizer: str | None = None  # one of TOKENIZERS
    max_tokens: Annotated[int | None, Field(ge=MAX_TOKENS_RANGE[0], le=MAX_TOKENS_RANGE[1])] = None  # hybrid
    merge_peers: bool | None = None  # hybrid

    def requested(self) -> RequestedChunking:
        return RequestedChunking(self.chunker, self.tokenizer, self.max_tokens, self.merge_peers)
