"""What lives in memory."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum


@dataclass(frozen=True)
class EmbeddableChunk:
    id: str  # the id of its node in data (FRAGMENTOS or EXP_CHUNK), never built here
    text: str  # texto_contextualizado: its headings in front of the text (texto_con_contexto in piaa-rag)


@dataclass(frozen=True)
class VectorIndexSpec:
    """A vector index as embeddings asks data for it: data creates and checks it, but never names it."""

    name: str  # built by domain/indexes.py, never written by hand
    label: str  # the node label (FRAGMENTOS or EXP_EMBED)
    property: str  # embedding_<model>_<dim> (feature 055): the model's own property
    dimensions: int


@dataclass(frozen=True)
class EmbeddableDocument:
    sha256: str
    chunked: bool  # estado_chunking is fragmentado: only those are embedded
    fingerprints: Mapping[str, str] = field(default_factory=dict)  # huella_embedding_<model>_<dim> → its value


class ConfigOrigin(StrEnum):
    """Where the active configuration came from. The VALUES are stored (CONFIG_OFICIAL.origen): Spanish."""

    DEFAULT = "defecto"
    EXPERIMENT = "experimento"
    MANUAL = "manual"


@dataclass(frozen=True)
class EmbeddingConfig:
    """The active configuration (this module's CONFIG_OFICIAL), or the one an experiment tries."""

    model: str
    max_tokens: int  # counting the model's special tokens
    origin: ConfigOrigin = ConfigOrigin.DEFAULT
    experiment: str | None = None  # the embeddings experiment it came from (or that tries it)
    modified: str | None = None
