"""What the parsing works with, in memory: a file as data has it (RAW), its parse state and what Docling gave."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum


class ParseStatus(StrEnum):
    """State of a document's parsing. The VALUES are stored (JSON `estado`, RAW `estado_parseo`): Spanish."""

    PARSED = "parseado"
    PARTIAL = "parcial"  # Docling stopped early (a timeout): what it reached is stored, the rest resumes later
    ERROR = "error"


@dataclass(frozen=True)
class PageCoverage:
    """Which pages of a file a parsing reached. All zero/empty for a format without pages (docx)."""

    total: int = 0
    processed: int = 0
    pending: list[int] = field(default_factory=list)  # pages it didn't reach: where a partial document resumes
    without_text: list[int] = field(default_factory=list)  # processed, with no text nor table even after OCR
    reason: str | None = None  # why the parsing stopped early

    @property
    def complete(self) -> bool:
        return not self.pending and self.reason is None


@dataclass(frozen=True)
class RawState:
    """A RAW without its content: whether its file is still chunkable and how its parsing went."""

    sha256: str
    vigente: bool = True
    status: ParseStatus | None = None  # None: never parsed
    fingerprint: str | None = None  # of the last parsing that got to store something


@dataclass(frozen=True)
class RawFile:
    """A RAW with its content: what is parsed."""

    sha256: str
    name: str
    type: str
    code: str | None
    content: bytes


@dataclass(frozen=True)
class StoredParse:
    """What a JSON node has of an earlier parsing: what a partial one resumes from."""

    document: Mapping[str, object]  # the DoclingDocument, as export_to_dict gives it
    coverage: PageCoverage
    status: ParseStatus
    fingerprint: str


@dataclass(frozen=True)
class ParsedOutput:
    """What the Parser gives for a file: the DoclingDocument (export_to_dict), the pages it reached and those that
    needed OCR to give any text."""

    document: Mapping[str, object]
    coverage: PageCoverage
    ocr_pages: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class PreviewSection:
    """A part of a previewed document: the path of titles it is under and its text (paragraphs, lists, tables)."""

    headings: list[str]
    text: str
    pages: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class PreviewDocument:
    """POST /preview (feature 048): a document read with the fixed configuration, kept nowhere."""

    name: str
    pages: int  # of the file (0 for a format without pages, like docx)
    truncated: bool  # only its first pages were read (PREVIEW_MAX_PAGES), or Docling stopped early
    text: str  # the sections one after the other, each one under its titles
    sections: list[PreviewSection]
