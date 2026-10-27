"""Ports of the chunking domain: where documents come from, where chunks go and who converts them.

The implementations live in adapters/ (the only package that imports docling and httpx, Ruff TID251); the domain
only depends on these interfaces and on the errors below, never on HTTP nor on Docling.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Protocol

from .batch import GraphBatch
from .concepts import (
    Chunk,
    ChunkedDocument,
    ChunkingParameters,
    ChunkPiece,
    ConversionParameters,
    ConvertedDocument,
    DocumentSection,
    OfficialDocument,
    ProcessedDocument,
    Score,
    Section,
    SourceDocument,
    StrategyParameters,
)
from .queries import DocumentPage, ExperimentDocument, ExperimentRecord, ExperimentSection
from .requests import DocumentFilter
from .stored import ConversionProperties


class SourceError(Exception):
    """The document source (ingesta) didn't answer or answered with an error: the run stops."""


class SinkError(Exception):
    """The chunk sink (data) didn't answer or failed: the run stops."""


class DocumentError(Exception):
    """A problem with one document only (ingesta doesn't have it, data rejected it): that document fails, the run
    goes on."""


class ConversionError(Exception):
    """The converter could not convert or chunk a document (or is not installed): that document fails."""


class ChunkSource(Protocol):
    """Where the documents to chunk come from (ingesta, feature 022)."""

    def pages(
        self, filter: DocumentFilter, per_page: int, first: int = 1, last: int | None = None
    ) -> Iterator[list[SourceDocument]]:
        """The chunkable documents that match `filter`, one page at a time (pages `first` to `last`, or to the end):
        the next page is only asked for when the caller asks for it. SourceError if the source changed between pages
        (they may have shifted)."""
        ...

    def find(self, sha256: str) -> SourceDocument:
        """The chunkable document with that content; DocumentError if there is none."""
        ...

    def content(self, document: SourceDocument) -> bytes:
        """The bytes of the document; DocumentError if the source no longer has it."""
        ...


class ChunkSink(Protocol):
    """Where the chunks are stored (the graph through data, feature 022)."""

    def save(self, batch: GraphBatch) -> int:
        """Writes the batch all or nothing (the document as chunked or as failed); returns the nodes written.
        DocumentError if data rejects it."""
        ...

    def processed(self) -> dict[str, ProcessedDocument]:
        """What is already stored, by origin."""
        ...

    def discard(self, sha256: str) -> None:
        """Deletes a document that was replaced by another content of the same origin, with what hangs from it."""
        ...


class ChunkCatalog(Protocol):
    """Reads what is stored (for GET /chunking/documents)."""

    def documents(self, page: int, per_page: int) -> DocumentPage: ...

    def document(self, sha256: str) -> ProcessedDocument | None: ...

    def chunks(self, sha256: str) -> tuple[list[Section], list[Chunk]]:
        """The sections and the chunks of a stored document, in order."""
        ...


class ServiceProbe(Protocol):
    """Checks whether another module of the server answers (for GET /chunking/health)."""

    def responds(self, path: str) -> bool:
        """True if GET <path> (relative to the server, e.g. /ingesta/health) answers 2xx."""
        ...


class Converter(ABC):
    """Converts a document and splits it into chunks (Docling, feature 023)."""

    @abstractmethod
    def available(self) -> bool:
        """True if the converter is installed (without loading it)."""

    @abstractmethod
    def version(self) -> str | None:
        """Version of the converter, or None if it is not installed."""

    @abstractmethod
    def chunk(self, name: str, content: bytes, parameters: ChunkingParameters) -> ChunkedDocument:
        """Converts `content` (a file called `name`) and chunks it (production runs, feature 023); ConversionError if
        it can't."""

    @abstractmethod
    def convert(self, name: str, content: bytes, parameters: ConversionParameters) -> ConvertedDocument:
        """Converts `content` into a document organized by its main titles (experiments, feature 025);
        ConversionError if it can't."""


class SectionChunker(Protocol):
    """Cuts a section of a converted document with a strategy (experiments, feature 025). Needs no Docling: only the
    tokenizer (and, for `semantic`, a local embedding model)."""

    def available(self) -> bool:
        """True if what it needs is installed (without loading it)."""
        ...

    def chunk(self, section: DocumentSection, parameters: StrategyParameters) -> list[ChunkPiece]:
        """The chunks of the section; ConversionError if it can't (a model that can't be loaded...)."""
        ...


class SelectionStore(Protocol):
    """What resolving the files of an experiment reads from the record (ExperimentRunner.resolve)."""

    def documents(self, experiment_id: str) -> list[ExperimentDocument]: ...

    def source(self, conversion_id: str) -> SourceDocument | None:
        """What ingesta said of the file of a stored conversion (to repeat its documents in another experiment)."""
        ...

    def has_conversion(self, conversion_id: str) -> bool: ...

    def official(self, sha256: str) -> OfficialDocument | None:
        """The official JSON of a document (feature 028), or None if it has none."""
        ...

    def official_pages(
        self, per_page: int, first: int = 1, last: int | None = None
    ) -> Iterator[list[OfficialDocument]]:
        """The JSON nodes of the official graph, a page at a time (pages `first` to `last`, or to the end); a JSON
        node that wasn't promoted (no `contenido`) comes with `content` None."""
        ...


class RecordingStore(Protocol):
    """What running an experiment needs: reuse a conversion and record each step (ExperimentRunner.run)."""

    def save(self, batch: GraphBatch) -> None:
        """Writes the batch all or nothing; DocumentError if data rejects it."""
        ...

    def conversion(self, conversion_id: str) -> ConvertedDocument | None:
        """A conversion already stored (EXP_DOCUMENTO converted without error), or None."""
        ...


class PromotionStore(Protocol):
    """What promoting an experiment to the official graph reads and writes (Promotion.run, feature 028)."""

    def documents(self, experiment_id: str) -> list[ExperimentDocument]: ...

    def save(self, batch: GraphBatch) -> None: ...

    def stored_conversion(self, conversion_id: str) -> ConversionProperties | None:
        """An EXP_DOCUMENTO as stored (to promote it to an official JSON, feature 028), or None."""
        ...

    def official(self, sha256: str) -> OfficialDocument | None: ...

    def sections(self, experiment_id: str, document: ExperimentDocument) -> list[ExperimentSection]: ...

    def chunks(self, experiment_id: str, document: ExperimentDocument) -> list[tuple[int, ChunkPiece]]:
        """(section index, chunk) of a document in an experiment, in order."""
        ...


class ExperimentStore(SelectionStore, RecordingStore, PromotionStore, Protocol):
    """The whole experiment record in the graph (through data, feature 025): the roles above and what the API reads
    and changes (experiments, their stored conversions, their scores). The domain asks only for the role it uses."""

    def experiment(self, id: str) -> ExperimentRecord | None: ...

    def experiments(self) -> list[ExperimentRecord]:
        """Every experiment in the graph, newest first."""
        ...

    def content(self, conversion_id: str) -> str | None:
        """The stored JSON of a conversion (its `contenido`), as stored."""
        ...

    def conversion_json(self, conversion_id: str) -> str | None:
        """The parameters of a stored conversion, as the JSON stored."""
        ...

    def delete(self, id: str) -> bool:
        """Deletes the experiment, its sections, chunks and scores (never the EXP_DOCUMENTO); False if there was
        none."""
        ...

    def scores(self, experiment_id: str) -> list[Score]:
        """The scores of an experiment, oldest first."""
        ...

    def score(self, experiment_id: str, score_id: str) -> Score | None: ...

    def save_score(self, experiment_id: str, score: Score) -> None: ...

    def delete_score(self, experiment_id: str, score_id: str) -> bool: ...
