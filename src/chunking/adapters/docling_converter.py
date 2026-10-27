"""Converter on top of IBM's Docling (optional `chunk` extra, features 023 and 025). The only file that uses docling
(Ruff TID251), always loaded inside the methods (deferred, with import_module): without the extra, the rest of the
server keeps working and type-checks. Docling is untyped from here on (Any is admitted in adapters/).

    content → DocumentStream → DocumentConverter(OCR off, table_structure, table_mode; CPU) → DoclingDocument
      chunk (023):   → HybridChunker(tokenizer, max_tokens, merge_peers, repeat_table_header) → chunks
      convert (025): → ConvertedDocument: sections by the titles of heading_level (DocumentWalker)

One DocumentConverter (layout models) per conversion options and one HybridChunker per its options are built once and
reused: loading them is the slow part. Docling's own models (layout, tables) go to the Hugging Face cache the first
time; tokenizers to TOKENIZER_CACHE (strategies.tools).
"""

import re
import threading
from collections.abc import Iterable, Iterator
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from importlib.util import find_spec
from io import BytesIO

from chunking.config import DOCUMENT_TIMEOUT
from chunking.models import (
    Chunk,
    ChunkedDocument,
    ChunkingParameters,
    ConversionError,
    ConversionParameters,
    ConvertedDocument,
    Converter,
    DocumentSection,
    Element,
    ElementKind,
    Inclusion,
    TableMode,
)

from .strategies import Docling, Models

MISSING = "Docling is not installed: uv sync --extra chunk"
_ACCEPTED = {"success", "partial_success"}  # docling's ConversionStatus values that leave a document
_ROMAN_TITLE = re.compile(r"^[IVXLC]+[.)]$")  # "I.", "IV)": a title of level 1 (numbered_titles)
_ROMAN_SUBTITLE = re.compile(r"^[IVXLC]+[.)]\d+[.)]?$")  # "III.1.": level 2
_GROUPS = {"list", "ordered_list", "unspecified", "chapter", "section", "key_value_area", "form_area", "picture_area"}
_SPACE_BEFORE_PUNCTUATION = re.compile(r"\s+([:;,.])")


def _pages(item: Docling) -> list[int]:
    return sorted({int(p.page_no) for p in getattr(item, "prov", None) or []})


class DocumentWalker:
    """Walks a DoclingDocument in reading order and builds the ConvertedDocument: a title of level <= heading_level
    (or a Roman-numbered list item, with numbered_titles) starts a section; deeper titles are subtitles inside it."""

    def __init__(self, document: Docling, parameters: ConversionParameters) -> None:
        self._doc = document
        self._parameters = parameters
        self._include: Inclusion = parameters.include
        self._title = ""
        self._sections: list[DocumentSection] = []
        self._current: tuple[str, int, list[Element]] = ("", 0, [])

    def build(self) -> ConvertedDocument:
        if self._include.page_headers or self._include.page_footers:
            for element in self._walk(self._doc.furniture):
                self._current[2].append(element)
        for element in self._walk(self._doc.body):
            self._current[2].append(element)
        self._close()
        return ConvertedDocument(self._title, self._sections)

    def _close(self) -> None:
        title, level, elements = self._current
        if title or elements:
            pages = sorted({p for e in elements for p in e.pages})
            self._sections.append(DocumentSection(title, level, pages, elements))

    def _heading(self, text: str, level: int, pages: list[int]) -> Iterator[Element]:
        """A title: starts a section (level <= heading_level) or is a subtitle element."""
        text = text.strip().rstrip(":").strip()
        if not text:
            return
        if level <= self._parameters.heading_level:
            self._close()
            self._current = (text, level, [])
        else:
            yield Element(ElementKind.SUBTITLE, text, pages)

    def _inline_text(self, node: Docling) -> str:
        texts = [str(getattr(i, "text", "") or "") for i, _ in self._doc.iterate_items(root=node, with_groups=False)]
        return _SPACE_BEFORE_PUNCTUATION.sub(r"\1", " ".join(t for t in texts if t.strip())).strip()

    def _inline_pages(self, node: Docling) -> list[int]:
        return sorted({p for i, _ in self._doc.iterate_items(root=node, with_groups=False) for p in _pages(i)})

    def _walk(self, node: Docling) -> Iterator[Element]:
        yield from self._items(ref.resolve(self._doc) for ref in getattr(node, "children", None) or [])

    def _items(self, items: Iterable[Docling]) -> Iterator[Element]:
        for item in items:
            label = str(getattr(item.label, "value", item.label))
            if label == "inline":
                text = self._inline_text(item)
                if text:
                    yield Element(ElementKind.PARAGRAPH, text, self._inline_pages(item))
            elif label in _GROUPS:
                yield from self._walk(item)
            elif label == "table":
                yield from self._table(item)
            elif label == "picture":
                caption = str(item.caption_text(self._doc) or "").strip()
                if self._include.pictures and caption:
                    yield Element(ElementKind.PICTURE, caption, _pages(item))
            elif label in ("page_header", "page_footer"):
                kind = ElementKind.PAGE_HEADER if label == "page_header" else ElementKind.PAGE_FOOTER
                wanted = self._include.page_headers if label == "page_header" else self._include.page_footers
                if wanted and str(item.text).strip():
                    yield Element(kind, str(item.text).strip(), _pages(item))
            elif label == "list_item":
                yield from self._list_item(item)
            elif label == "section_header":
                yield from self._heading(str(item.text), int(getattr(item, "level", 1) or 1), _pages(item))
            elif label == "title":
                self._title = self._title or str(item.text).strip()
                yield from self._heading(str(item.text), 0, _pages(item))
            else:
                text = str(getattr(item, "text", "") or "").strip()
                if text:
                    yield Element(ElementKind.PARAGRAPH, text, _pages(item))
                yield from self._walk(item)

    def _table(self, item: Docling) -> Iterator[Element]:
        """A data table as Markdown; a layout table (Word templates: cells holding paragraphs, lists, titles) is
        walked like any other content."""
        captions = {c.cref for c in getattr(item, "captions", None) or []}
        if any(c.cref not in captions for c in item.children or []):
            yield from self._walk(item)
        elif self._include.tables:
            text = str(item.export_to_markdown(doc=self._doc)).strip()
            if text:
                yield Element(ElementKind.TABLE, text, _pages(item))

    def _list_item(self, item: Docling) -> Iterator[Element]:
        marker = str(getattr(item, "marker", "") or "").strip()
        inline = [c.resolve(self._doc) for c in item.children or []]
        inline = [c for c in inline if str(getattr(c.label, "value", c.label)) == "inline"]
        text = str(item.text or "").strip() or " ".join(self._inline_text(c) for c in inline).strip()
        pages = _pages(item) or sorted({p for c in inline for p in self._inline_pages(c)})
        if self._parameters.numbered_titles and _ROMAN_TITLE.match(marker):
            yield from self._heading(text, 1, pages)
        elif self._parameters.numbered_titles and _ROMAN_SUBTITLE.match(marker):
            yield from self._heading(text, 2, pages)
        elif self._include.lists and text:
            yield Element(ElementKind.LIST_ITEM, text, pages, marker or None)
        nested = [c.resolve(self._doc) for c in item.children or []]  # a nested list, under the item
        yield from self._items(c for c in nested if str(getattr(c.label, "value", c.label)) != "inline")


class DoclingConverter(Converter):
    def __init__(self, models: Models | None = None) -> None:
        self._models = models or Models()
        self._lock = threading.Lock()  # building the converters and the chunkers (one run or experiment at a time)
        self._converters: dict[tuple[bool, str], Docling] = {}
        self._chunkers: dict[tuple[str, int, bool, bool], Docling] = {}

    def available(self) -> bool:
        return find_spec("docling") is not None  # finds the package without importing it (Docling loads PyTorch)

    def version(self) -> str | None:
        try:
            return version("docling")
        except PackageNotFoundError:
            return None

    def _document(self, name: str, content: bytes, table_structure: bool, table_mode: TableMode) -> Docling:
        """The DoclingDocument of `content`; ConversionError if Docling can't convert it."""
        if not self.available():
            raise ConversionError(MISSING)
        with self._lock:
            converter = self._document_converter(table_structure, table_mode)
        stream = import_module("docling_core.types.io").DocumentStream(name=name, stream=BytesIO(content))
        result = converter.convert(stream, raises_on_error=True)
        status = str(getattr(result.status, "value", result.status))
        if status not in _ACCEPTED:
            errors = "; ".join(str(getattr(e, "error_message", e)) for e in result.errors or [])
            raise ConversionError(f"Docling could not convert it ({status}): {errors or 'no reason given'}")
        return result.document

    def chunk(self, name: str, content: bytes, parameters: ChunkingParameters) -> ChunkedDocument:
        try:
            document = self._document(name, content, parameters.table_structure, parameters.table_mode)
            chunker = self._hybrid_chunker(parameters)
            chunks = [self._chunk(i, c, chunker) for i, c in enumerate(chunker.chunk(document))]
        except ConversionError:
            raise
        except Exception as e:  # anything Docling raises (corrupt, protected, timeout, unsupported format...)
            raise ConversionError(f"{type(e).__name__}: {e}".strip()) from e
        oversized = [c.index for c in chunks if c.tokens > parameters.max_tokens]
        if oversized:  # the promise is that no chunk goes over max_tokens: never store one that does
            hint = " (repeat_table_header can do that: try it off)" if parameters.repeat_table_header else ""
            raise ConversionError(f"chunks {oversized} have more than {parameters.max_tokens} tokens{hint}")
        return ChunkedDocument(chunks)

    def convert(self, name: str, content: bytes, parameters: ConversionParameters) -> ConvertedDocument:
        try:
            document = self._document(name, content, parameters.table_structure, parameters.table_mode)
            return DocumentWalker(document, parameters).build()
        except ConversionError:
            raise
        except Exception as e:
            raise ConversionError(f"{type(e).__name__}: {e}".strip()) from e

    def _document_converter(self, table_structure: bool, table_mode: TableMode) -> Docling:
        key = (table_structure, table_mode.value)
        if key not in self._converters:
            converter = import_module("docling.document_converter")
            options = import_module("docling.datamodel.pipeline_options")
            accelerator = import_module("docling.datamodel.accelerator_options")
            formats = import_module("docling.datamodel.base_models")
            pdf = options.PdfPipelineOptions(
                do_ocr=False,  # scanned documents give no text: they end as an error (OCR is in the backlog)
                do_table_structure=table_structure,
                table_structure_options=options.TableStructureOptions(mode=options.TableFormerMode(table_mode.value)),
                document_timeout=DOCUMENT_TIMEOUT,
                accelerator_options=accelerator.AcceleratorOptions(device=accelerator.AcceleratorDevice.CPU),
            )
            self._converters[key] = converter.DocumentConverter(
                format_options={formats.InputFormat.PDF: converter.PdfFormatOption(pipeline_options=pdf)}
            )
        return self._converters[key]

    def _hybrid_chunker(self, parameters: ChunkingParameters) -> Docling:
        key = (parameters.tokenizer, parameters.max_tokens, parameters.merge_peers, parameters.repeat_table_header)
        tokenizer = self._models.tokens(parameters.tokenizer).tokenizer
        with self._lock:
            if key not in self._chunkers:
                huggingface = import_module("docling_core.transforms.chunker.tokenizer.huggingface")
                hybrid = import_module("docling_core.transforms.chunker.hybrid_chunker")
                # repeat_table_header=True may go over max_tokens: docling-core splits a table counting only its text,
                # and the headings contextualize puts in front push the chunk over (the guard then fails the document).
                self._chunkers[key] = hybrid.HybridChunker(
                    tokenizer=huggingface.HuggingFaceTokenizer(tokenizer=tokenizer, max_tokens=parameters.max_tokens),
                    merge_peers=parameters.merge_peers,
                    repeat_table_header=parameters.repeat_table_header,
                )
            return self._chunkers[key]

    @staticmethod
    def _chunk(index: int, chunk: Docling, chunker: Docling) -> Chunk:
        contextualized = str(chunker.contextualize(chunk=chunk))
        pages = {prov.page_no for item in chunk.meta.doc_items for prov in (getattr(item, "prov", None) or [])}
        return Chunk(
            index=index,
            text=str(chunk.text),
            contextualized_text=contextualized,
            headings=[str(h) for h in chunk.meta.headings or []],
            pages=sorted(int(p) for p in pages),
            tokens=int(chunker.tokenizer.count_tokens(contextualized)),
        )
