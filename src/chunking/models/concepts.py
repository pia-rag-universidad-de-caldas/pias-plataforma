"""Chunking domain concepts that live in memory (feature 043): what is chunked (a parsed document of data), with which
parameters, and what comes out (chunks grouped by their headings)."""

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum


class DoclingChunker(StrEnum):
    """The chunkers of docling-core. The VALUES are stored (on the JSON and the EXPERIMENTO)."""

    HYBRID = "hybrid"  # sized: splits what goes over max_tokens and merges small neighbours with the same headings
    HIERARCHICAL = "hierarchical"  # one chunk per element of the document (paragraph, table, whole list)
    PAGE = "page"  # one chunk per page


@dataclass(frozen=True)
class RequestedChunking:
    """The configurable part as asked for; None = not asked (CHUNKING_DEFAULT, if the chunker uses it)."""

    chunker: DoclingChunker | None = None
    tokenizer: str | None = None
    max_tokens: int | None = None
    merge_peers: bool | None = None


@dataclass(frozen=True)
class ChunkingParameters:
    """Everything that decides how a document is chunked: the configurable part, resolved (max_tokens and merge_peers
    are None unless the chunker is `hybrid`), and the versions of what is fixed."""

    chunker: DoclingChunker
    tokenizer: str  # counts the tokens of every chunk (every chunker)
    max_tokens: int | None
    merge_peers: bool | None
    chunking_version: int  # CHUNKING_VERSION
    docling_version: str  # of docling-core

    @property
    def fingerprint(self) -> str:
        """Stable short hash of ALL the parameters."""
        text = json.dumps(asdict(self), sort_keys=True)
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def configurable(self) -> dict[str, str | int | bool]:
        """The part a request asks for, without what this chunker doesn't use."""
        asked = {
            "chunker": self.chunker.value,
            "tokenizer": self.tokenizer,
            "max_tokens": self.max_tokens,
            "merge_peers": self.merge_peers,
        }
        return {k: v for k, v in asked.items() if v is not None}


def chunked_fingerprint(parameters: ChunkingParameters, parse_fingerprint: str) -> str:
    """What makes a document already chunked: the same parameters over the same parse."""
    text = f"{parameters.fingerprint}:{parse_fingerprint}"
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class ConfigOrigin(StrEnum):
    """Where the active configuration came from. The VALUES are stored (CONFIG_OFICIAL.origen)."""

    DEFAULT = "defecto"
    EXPERIMENT = "experimento"
    MANUAL = "manual"


@dataclass(frozen=True)
class ActiveConfig:
    """The active configuration: what POST /chunking/runs chunks with."""

    requested: RequestedChunking
    origin: ConfigOrigin
    experiment: str | None = None  # with origin EXPERIMENT
    modified: str | None = None  # ISO; None for the default (nobody set it)


@dataclass(frozen=True)
class ParsedDocument:
    """A JSON node of data, as parsing left it (feature 042) and with what chunking stored on it."""

    sha256: str
    status: str  # the parse's `estado`: parseado, parcial, error
    parse_fingerprint: str
    content: str | None  # the DoclingDocument as JSON text (decoded), or None if the node has none
    chunked: str | None = None  # chunked_fingerprint of its official chunks, if it has them
    chunks: int = 0
    configuration: str | None = None  # config_chunking: what data counts with (None if chunked before feature 045)

    @property
    def parsed(self) -> bool:
        return self.content is not None and self.status in ("parseado", "parcial")


@dataclass(frozen=True)
class Section:
    """A distinct heading path of a document; the chunks without a heading go to the root one (no headings)."""

    order: int  # by first appearance in the document, from 0
    headings: list[str]


@dataclass(frozen=True)
class Chunk:
    index: int  # position in the document, from 0
    text: str
    contextualized_text: str  # text with its headings in front (what gets embedded)
    headings: list[str]
    pages: list[int]
    tokens: int  # of contextualized_text, counted with the tokenizer of the parameters
