"""What the domain asks of the outside (data and Docling), and the errors of each side."""

from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping, Sequence
from typing import Protocol

from .batch import GraphBatch
from .concepts import ParsedOutput, RawFile, RawState, StoredParse


class SinkError(Exception):
    """data doesn't answer (or answers something unexpected): it stops the run."""


class DocumentError(Exception):
    """data refused what was written or asked for one document: only that one fails."""


class ParseError(Exception):
    """The document's fault (corrupt, protected, unsupported...): only that one fails."""


class ParserUnavailable(Exception):
    """The machine's fault (Docling or its models don't load, no memory nor disk): it stops the run, nothing written."""


class RawSource(Protocol):
    def states(self, sha256s: Sequence[str]) -> Mapping[str, RawState]:
        """The RAW of those sha256 that data has, without their content."""
        ...

    def all_states(self) -> Iterator[RawState]:
        """Every RAW, without its content, a page at a time."""
        ...

    def get(self, sha256: str) -> RawFile | None:
        """The RAW with its content; None if data doesn't have it."""
        ...


class ParsedSink(Protocol):
    def previous(self, sha256: str) -> StoredParse | None:
        """What the JSON of that sha256 has of an earlier parsing; None if there is none (or it can't be read)."""
        ...

    def save(self, batch: GraphBatch) -> None:
        """All or nothing; DocumentError if data refuses it, SinkError if it doesn't answer."""
        ...


class RunStore(Protocol):
    """The record of the runs (CORRIDA_PARSEO): each one as the JSON GET /runs answers."""

    def save(self, id: str, status: str, requested: str, detail: str) -> None: ...

    def details(self) -> list[str]:
        """Every stored run, as its JSON."""
        ...

    def detail(self, id: str) -> str | None: ...


class Parser(ABC):
    @abstractmethod
    def available(self) -> bool:
        """Whether Docling is installed."""

    @abstractmethod
    def version(self) -> str | None:
        """Docling's version; None if it isn't installed."""

    @abstractmethod
    def ocr_available(self) -> bool:
        """Whether the OCR engine is installed."""

    @abstractmethod
    def parse(self, name: str, content: bytes, previous: StoredParse | None = None) -> ParsedOutput:
        """The DoclingDocument of `content`; with a partial `previous`, only its pending pages, joined to it.
        ParseError if it is the document's fault, ParserUnavailable if it is the machine's."""

    def preview(self, name: str, content: bytes, max_pages: int) -> ParsedOutput:
        """`content` read to show it (POST /preview), with the same configuration; of a PDF, only its first
        `max_pages` pages (the coverage says how many it has). By default the whole parse."""
        return self.parse(name, content)
