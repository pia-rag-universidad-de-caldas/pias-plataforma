"""Chunking domain concepts that live in memory: what is chunked and with which parameters, what Docling's conversion
gives (feature 025), how a section is cut, and the scores of experiments."""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from enum import StrEnum


@dataclass(frozen=True)
class SourceDocument:
    """A chunkable file as ingesta describes it (one row of GET /ingesta/data or GET /ingesta/data/file)."""

    origin: str  # relative path in base/: the file identity, the way back to the original
    target: str  # relative path in ingesta/
    name: str  # original file name (its extension tells Docling the format)
    sha256: str | None  # content identity; None only if ingesta never hashed it (it can't be chunked then)
    file_type: str  # normalized extension (pdf, doc, docx)
    year: int | None
    code: str | None  # PIAA code; None if the path is incomplete


class TableMode(StrEnum):
    """Docling's TableFormer mode (values as Docling's)."""

    ACCURATE = "accurate"
    FAST = "fast"


@dataclass(frozen=True)
class ChunkingParameters:
    """Everything that decides how a production run (feature 023, Docling's HybridChunker) chunks a document; if any
    of it changes, the document is chunked again."""

    tokenizer: str
    max_tokens: int
    merge_peers: bool  # merge small consecutive chunks with the same headings
    repeat_table_header: bool  # repeat a split table's header rows in each piece
    table_structure: bool  # table structure model on PDFs
    table_mode: TableMode
    docling_version: str

    @property
    def fingerprint(self) -> str:
        """Stable short hash of ALL the parameters (stored with each chunked document)."""
        text = json.dumps(asdict(self), sort_keys=True)
        return hashlib.sha256(text.encode()).hexdigest()[:16]


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


@dataclass(frozen=True)
class ChunkedDocument:
    """What the Converter returns for a document: its chunks, in order (Hierarchy groups them into sections)."""

    chunks: list[Chunk]


class DocumentStatus(StrEnum):
    """Status of a document in the graph. The VALUES are stored in Neo4j: they stay in Spanish."""

    CHUNKED = "fragmentado"
    ERROR = "error"
    CONVERTED = "convertido"  # converted to JSON, not chunked (a conversion-only experiment, an official JSON; 028)


@dataclass(frozen=True)
class ProcessedDocument:
    """What the graph has of a document (its JSON node): to decide whether it is pending and to list it."""

    origin: str
    sha256: str
    fingerprint: str
    status: DocumentStatus
    target: str | None = None
    file_type: str | None = None
    year: int | None = None
    code: str | None = None
    error: str | None = None
    chunked_at: str | None = None  # ISO, when it was chunked (or failed)
    chunks: int = 0
    parameters: ChunkingParameters | None = None  # the ones it was chunked with (None if the node lacks them)


@dataclass(frozen=True)
class Inclusion:
    """Which kinds of element the converted document keeps."""

    tables: bool = True
    lists: bool = True
    page_headers: bool = False
    page_footers: bool = False
    pictures: bool = False  # only their caption (there is no OCR)


@dataclass(frozen=True)
class ConversionParameters:
    heading_level: int  # titles of this level or above (1 = the main ones) start a section
    numbered_titles: bool  # list items numbered with Roman numerals ("I.", "III.1.") are titles (Word templates)
    table_structure: bool
    table_mode: TableMode
    include: Inclusion
    docling_version: str

    @property
    def fingerprint(self) -> str:
        """Stable short hash of ALL the parameters: same file + same fingerprint = same conversion (reused)."""
        text = json.dumps(asdict(self), sort_keys=True)
        return hashlib.sha256(text.encode()).hexdigest()[:16]


class ElementKind(StrEnum):
    """Kinds of element in a converted document. The VALUES are stored (the `contenido` JSON): Spanish."""

    PARAGRAPH = "parrafo"
    LIST_ITEM = "item"  # one point of a list (with its `marcador`: "1.", "a)", "•"...)
    TABLE = "tabla"  # as Markdown
    SUBTITLE = "subtitulo"  # a title below heading_level: inside the section
    PICTURE = "imagen"  # its caption
    PAGE_HEADER = "encabezado_pagina"
    PAGE_FOOTER = "pie_pagina"


@dataclass(frozen=True)
class Element:
    kind: ElementKind
    text: str
    pages: list[int] = field(default_factory=list)
    marker: str | None = None  # list items: their enumeration or bullet


@dataclass(frozen=True)
class DocumentSection:
    """What hangs from one main title (the first one, `title` "", is what comes before any title)."""

    title: str
    level: int  # of its title (0 for the part before any title)
    pages: list[int]
    elements: list[Element]


@dataclass(frozen=True)
class ConvertedDocument:
    title: str  # the document title if Docling found one, else ""
    sections: list[DocumentSection]

    def to_json(self) -> str:
        """The stored form (EXP_DOCUMENTO.contenido): Spanish keys, as the rest of the stored data."""
        return json.dumps(
            {
                "titulo": self.title,
                "secciones": [
                    {
                        "titulo": s.title,
                        "nivel": s.level,
                        "paginas": s.pages,
                        "elementos": [
                            {"tipo": e.kind.value, "texto": e.text, "paginas": e.pages}
                            | ({"marcador": e.marker} if e.marker is not None else {})
                            for e in s.elements
                        ],
                    }
                    for s in self.sections
                ],
            },
            ensure_ascii=False,
        )

    @staticmethod
    def from_json(text: str) -> "ConvertedDocument":
        """Back from to_json; ValueError if it isn't that form."""
        try:
            data = json.loads(text)
            return ConvertedDocument(
                str(data["titulo"]),
                [
                    DocumentSection(
                        str(s["titulo"]),
                        int(s["nivel"]),
                        [int(p) for p in s["paginas"]],
                        [
                            Element(
                                ElementKind(e["tipo"]),
                                str(e["texto"]),
                                [int(p) for p in e["paginas"]],
                                str(e["marcador"]) if e.get("marcador") is not None else None,
                            )
                            for e in s["elementos"]
                        ],
                    )
                    for s in data["secciones"]
                ],
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"not a converted document: {error}") from error


class ChunkingStrategy(StrEnum):
    """The VALUES are stored (EXP_SECCION.estrategia)."""

    HYBRID = "hybrid"  # consecutive elements joined up to max_tokens; those over it are split
    ELEMENT = "element"  # one chunk per element (paragraph, list item, table); no max_tokens
    SECTION = "section"  # the whole section, split if over max_tokens
    PAGE = "page"  # one chunk per page of the section (split if over max_tokens)
    FIXED = "fixed"  # windows of max_tokens with overlap_tokens, ignoring the elements
    POINTS = "points"  # one chunk per list item or numeral; the rest by paragraphs
    SEMANTIC = "semantic"  # consecutive elements joined while their embeddings stay similar


@dataclass(frozen=True)
class StrategyParameters:
    """The resolved parameters of one strategy; the ones it doesn't use are None."""

    strategy: ChunkingStrategy
    tokenizer: str  # counts the tokens (every strategy)
    max_tokens: int | None  # None only for element
    merge_peers: bool | None  # hybrid
    overlap_tokens: int | None  # fixed
    embedding_model: str | None  # semantic
    similarity_threshold: float | None  # semantic


@dataclass(frozen=True)
class ChunkPiece:
    """A chunk cut from a section."""

    text: str
    headings: list[str]  # the section title and the subtitle it falls under, if any
    pages: list[int]
    tokens: int


@dataclass(frozen=True)
class OfficialDocument:
    """An official JSON node (feature 028): the file, the conversion it was promoted from and its content."""

    document: SourceDocument
    conversion_id: str  # the EXP_DOCUMENTO it came from
    conversion_json: str | None  # its ConversionParameters, as stored
    docling: str
    content: ConvertedDocument | None  # None if the node has no (readable) `contenido`


@dataclass(frozen=True)
class ExperimentFile:
    """A file that enters an experiment, and whether its conversion already exists (reused, without Docling)."""

    document: SourceDocument
    reused: bool
    conversion_id: str  # its EXP_DOCUMENTO: <sha256>:<conversion fingerprint>
    official: OfficialDocument | None = None  # an official JSON (feature 028): its content is never converted again


@dataclass(frozen=True)
class SectionAssignment:
    """Which rule took a section (None = the plan's default) and with which strategy it is cut."""

    index: int
    section: DocumentSection
    rule: int | None
    parameters: StrategyParameters


@dataclass(frozen=True)
class Score:
    id: str
    criteria: dict[str, float]  # free: name → value in SCORE_MIN–SCORE_MAX
    created: str  # ISO
    modified: str  # ISO
    author: str | None = None
    comment: str | None = None
    target: str | None = None  # reserved: a document, section or chunk of the experiment (not used yet)
