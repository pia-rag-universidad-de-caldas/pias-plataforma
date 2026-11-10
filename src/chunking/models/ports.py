"""Ports of the chunking domain (feature 043): where the parsed documents are and where the chunks go (data, the only
module chunking talks to), and who chunks them (docling-core).

The implementations live in adapters/ (the only package that imports docling_core and httpx, Ruff TID251); the domain
only depends on these interfaces and on the errors below, never on HTTP nor on docling-core.
"""

from abc import ABC, abstractmethod
from typing import Protocol

from .batch import GraphBatch
from .concepts import ActiveConfig, Chunk, ChunkingParameters, ParsedDocument
from .queries import DocumentUse, ExperimentRecord
from .results import ChunkingRun


class SinkError(Exception):
    """data didn't answer or failed: the experiment or the run stops."""


class DocumentError(Exception):
    """A problem with one document only (data rejected its batch): that document fails, the rest goes on."""


class ChunkingError(Exception):
    """The chunker could not chunk this document (its content isn't a DoclingDocument, a chunk over max_tokens):
    that document fails."""


class ChunkerUnavailable(Exception):
    """The machine can't chunk anything now (docling-core or the tokenizer can't be loaded): it isn't the document's
    fault, so nothing is written about it and the experiment or run stops."""


class NoConfiguration(Exception):
    """There is no configuration to chunk with: neither a valid stored one nor the default."""


class Chunker(ABC):
    """Chunks a DoclingDocument with docling-core's chunkers."""

    @abstractmethod
    def available(self) -> bool:
        """True if docling-core is installed (without loading it)."""

    @abstractmethod
    def version(self) -> str | None:
        """Version of docling-core, or None if it is not installed."""

    @abstractmethod
    def chunk(self, content: str, parameters: ChunkingParameters) -> list[Chunk]:
        """The chunks of `content` (a DoclingDocument as JSON text), in order; ChunkingError if it can't,
        ChunkerUnavailable if nothing can be chunked now."""


class DocumentStore(Protocol):
    """The parsed documents in data, and writing what hangs from them."""

    def document(self, sha256: str) -> ParsedDocument | None:
        """The JSON node of that content, or None if there is none."""
        ...

    def save(self, batch: GraphBatch) -> None:
        """Writes the batch all or nothing; DocumentError if data rejects it."""
        ...


class MissingDocuments(Protocol):
    """What is still to chunk with a configuration (data's GET /progress/chunking)."""

    def missing(self, fingerprint: str, page: int | None, per_page: int | None) -> list[str]:
        """The sha256s of the parsed JSON not chunked with the configuration of that fingerprint over their current
        parse, ordered by sha256: one page of them, or (page None) all."""
        ...


class ExperimentStore(DocumentStore, MissingDocuments, Protocol):
    """The experiment record in the graph (through data)."""

    def experiment(self, id: str) -> ExperimentRecord | None: ...

    def experiments(self) -> list[ExperimentRecord]:
        """Every experiment in the graph, newest first."""
        ...

    def documents(self, experiment_id: str) -> list[str]:
        """The sha256s of the documents an experiment used (its EXP_USA), in order."""
        ...

    def uses(self, experiment_id: str) -> list[DocumentUse]:
        """What the experiment did with each document it got to (its EXP_USA)."""
        ...

    def delete(self, id: str) -> bool:
        """Deletes the experiment, its sections and chunks (never the JSON); False if there was none."""
        ...

    def chunked_with(self) -> list[ChunkingParameters | None]:
        """For every JSON of the graph, the parameters its official chunks were made with (None: not chunked). Reads
        every JSON: slow."""
        ...


class ConfigStore(Protocol):
    """The active configuration (one CONFIG_OFICIAL node)."""

    def stored(self) -> ActiveConfig | None:
        """The one someone set, or None if nobody did (the default applies)."""
        ...

    def put(self, config: ActiveConfig) -> None: ...

    def clear(self) -> bool:
        """Back to the default; False if nobody had set one."""
        ...


class RunStore(Protocol):
    """The record of POST /runs (CORRIDA_CHUNKING), which outlives the server."""

    def save(self, batch: GraphBatch) -> None: ...

    def run(self, id: str) -> ChunkingRun | None: ...

    def runs(self) -> list[ChunkingRun]:
        """Newest first."""
        ...


class ServiceProbe(Protocol):
    """Checks whether another route of the server answers (for GET /chunking/health)."""

    def responds(self, path: str) -> bool:
        """True if GET <path> (relative to the server, e.g. /data/health) answers 2xx."""
        ...
