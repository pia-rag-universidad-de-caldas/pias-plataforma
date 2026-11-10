"""DoclingParser (feature 042): a file into a DoclingDocument with the fixed configuration (config/docling.py).
Docling is the `parse` extra: always imported inside the methods (deferred), so that the rest of the server works
without it.

    content → first pass (no OCR) → pages without text? → second pass, only those pages, OCR full page → joined
    a partial one (timeout) → only its pending pages → joined to what was stored
    Word → Roman-numbered list items become titles

One DocumentConverter per pass, built once and reused: loading the models is the slow part. What the machine lacks
(Docling, its models, memory, disk) is ParserUnavailable and stops a run; only what is the document's fault is
ParseError. The conversion logic comes from chunking's DoclingConverter (feature 023), which feature 043 removes.
"""

import errno
import shutil
import threading
from collections.abc import Mapping
from importlib import import_module
from importlib.metadata import PackageNotFoundError, version
from importlib.util import find_spec
from io import BytesIO

from parsing.config import PARSING, ParsingConfig
from parsing.models import PageCoverage, ParsedOutput, ParseError, Parser, ParserUnavailable, StoredParse

from .roman_titles import Docling, promote_roman_titles

MISSING = "Docling is not installed: uv sync --extra parse"
NO_LIBREOFFICE = "LibreOffice is not installed: Docling needs it to convert .doc files"
_COMPLETE = "success"
_ACCEPTED = {_COMPLETE, "partial_success"}  # docling's ConversionStatus values that leave a document
_NO_RESOURCES = {errno.ENOSPC, errno.ENOMEM, errno.EMFILE, errno.ENFILE}
_NO_MEMORY = ("out of memory", "can't allocate memory")


def is_infrastructure(error: BaseException) -> bool:
    """Whether what went wrong is the machine (no memory, no disk), looking at its causes too."""
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, MemoryError):
            return True
        if isinstance(current, OSError) and current.errno in _NO_RESOURCES:
            return True
        if isinstance(current, RuntimeError) and any(text in str(current).lower() for text in _NO_MEMORY):
            return True
        current = current.__cause__ or current.__context__
    return False


def pages_of(item: Docling) -> list[int]:
    return sorted({int(p.page_no) for p in getattr(item, "prov", None) or []})


def _has_text(item: Docling) -> bool:
    is_table = str(getattr(item.label, "value", item.label)) == "table"
    return is_table or bool(str(getattr(item, "text", "") or "").strip())


def text_pages(document: Docling) -> set[int]:
    """The pages where the document has some text or a table."""
    return {p for item, _ in document.iterate_items() if _has_text(item) for p in pages_of(item)}


def _reason(result: Docling) -> str:
    messages = dict.fromkeys(str(getattr(e, "error_message", e)) for e in result.errors or [])
    return "; ".join(messages) or "Docling converted only part of it"


def _status(result: Docling) -> str:
    return str(getattr(result.status, "value", result.status))


def joined(parts: list[tuple[Docling, set[int]]], pages: list[int], concatenate: Docling) -> Docling:
    """One document with, for each page, the items of the part that has it: consecutive pages of the same part go
    together (Docling's filter), in page order (concatenate)."""
    owner = {page: index for index, (_, owned) in enumerate(parts) for page in owned}
    runs: list[tuple[int, set[int]]] = []
    for page in pages:
        if page not in owner:
            continue
        if runs and runs[-1][0] == owner[page]:
            runs[-1][1].add(page)
        else:
            runs.append((owner[page], {page}))
    if not runs:  # no page has items of any part: the first part as it is (an empty document)
        return parts[0][0]
    return concatenate([parts[index][0].filter(page_nrs=owned) for index, owned in runs])


class DoclingParser(Parser):
    def __init__(self, config: ParsingConfig = PARSING) -> None:
        self._config = config
        self._lock = threading.Lock()
        # One conversion at a time on these converters (runs and previews share them): their models aren't safe to
        # use from two threads at once, and two would double the memory.
        self._converting = threading.Lock()
        self._converters: dict[bool, Docling] = {}  # by OCR: the first pass and the second one

    def available(self) -> bool:
        return find_spec("docling") is not None  # without importing it (Docling loads PyTorch)

    def ocr_available(self) -> bool:
        return find_spec("onnxruntime") is not None and find_spec("rapidocr") is not None

    def version(self) -> str | None:
        try:
            return version("docling")
        except PackageNotFoundError:
            return None

    def unavailable_types(self) -> dict[str, str]:
        return {} if shutil.which("soffice") or shutil.which("libreoffice") else {"doc": NO_LIBREOFFICE}

    def _converter(self, ocr: bool) -> Docling:
        """A converter with its models loaded: nothing here depends on a document, so any failure is the machine's."""
        if not self.available():
            raise ParserUnavailable(MISSING)
        try:
            with self._lock:
                if ocr not in self._converters:
                    self._converters[ocr] = self._build(ocr)
                return self._converters[ocr]
        except Exception as e:
            raise ParserUnavailable(f"Docling can't be loaded: {type(e).__name__}: {e}".strip()) from e

    def _build(self, ocr: bool) -> Docling:
        config = self._config
        converter = import_module("docling.document_converter")
        options = import_module("docling.datamodel.pipeline_options")
        accelerator = import_module("docling.datamodel.accelerator_options")
        formats = import_module("docling.datamodel.base_models")
        ocr_options = (
            options.RapidOcrOptions(mode=options.OcrMode.FULL_PAGE if config.ocr_full_page else options.OcrMode.DEFAULT)
            if ocr
            else options.OcrAutoOptions()
        )
        pdf = options.PdfPipelineOptions(
            do_ocr=ocr,
            ocr_options=ocr_options,
            do_table_structure=config.table_structure,
            table_structure_options=options.TableStructureOptions(
                do_cell_matching=config.cell_matching, mode=options.TableFormerMode(config.table_mode)
            ),
            document_timeout=config.document_timeout,
            accelerator_options=accelerator.AcceleratorOptions(device=accelerator.AcceleratorDevice(config.device)),
            do_picture_description=config.picture_description,
            do_picture_classification=config.picture_classification,
            do_formula_enrichment=config.formula_enrichment,
            do_code_enrichment=config.code_enrichment,
            do_chart_extraction=config.chart_extraction,
        )
        pdf.heading_hierarchy_options.enabled = config.heading_hierarchy
        built = converter.DocumentConverter(
            format_options={formats.InputFormat.PDF: converter.PdfFormatOption(pipeline_options=pdf)}
        )
        built.initialize_pipeline(formats.InputFormat.PDF)  # loads the models: missing ones aren't a PDF's fault
        return built

    def _convert(self, ocr: bool, name: str, content: bytes, pages: list[int] | None) -> Docling:
        converter = self._converter(ocr)
        stream = import_module("docling_core.types.io").DocumentStream(name=name, stream=BytesIO(content))
        page_range = {"page_range": (min(pages), max(pages))} if pages else {}
        with self._converting:
            result = converter.convert(stream, raises_on_error=True, **page_range)
        status = _status(result)
        if status not in _ACCEPTED:
            errors = "; ".join(str(getattr(e, "error_message", e)) for e in result.errors or [])
            raise ParseError(f"Docling could not convert it ({status}): {errors or 'no reason given'}")
        return result

    def parse(self, name: str, content: bytes, previous: StoredParse | None = None) -> ParsedOutput:
        return self._parse(name, content, previous, None)

    def preview(self, name: str, content: bytes, max_pages: int) -> ParsedOutput:
        return self._parse(name, content, None, max_pages)

    def _parse(self, name: str, content: bytes, previous: StoredParse | None, limit: int | None) -> ParsedOutput:
        if name.lower().endswith(".doc") and "doc" in self.unavailable_types():
            raise ParseError(NO_LIBREOFFICE)
        try:
            if name.lower().endswith(".pdf"):
                return self._pdf(name, content, previous, limit)
            return self._other(name, content)
        except (ParseError, ParserUnavailable):
            raise
        except Exception as e:  # anything Docling raises (corrupt, protected, unsupported format...)
            message = f"{type(e).__name__}: {e}".strip()
            raise (ParserUnavailable(message) if is_infrastructure(e) else ParseError(message)) from e

    def _other(self, name: str, content: bytes) -> ParsedOutput:
        """Word and the rest: Docling doesn't convert them by pages, and they have no scanned pages."""
        result = self._convert(False, name, content, None)
        document = result.document
        if self._config.roman_titles:
            promote_roman_titles(document, import_module("docling_core.types.doc").SectionHeaderItem)
        reason = _reason(result) if _status(result) != _COMPLETE else None
        return ParsedOutput(document.export_to_dict(), PageCoverage(reason=reason))

    def _pdf(self, name: str, content: bytes, previous: StoredParse | None, limit: int | None) -> ParsedOutput:
        """`limit`: only the first pages (a preview); a run reads them all."""
        concatenate = import_module("docling_core.types.doc").DoclingDocument.concatenate
        pending = list(previous.coverage.pending) if previous else []
        first = list(range(1, limit + 1)) if limit and not pending else []
        result = self._convert(False, name, content, pending or first or None)
        total = int(result.input.page_count or 0)
        asked = set(pending) if pending else set(range(1, min(total, limit or total) + 1))
        reached = {int(page.page_no) for page in result.pages or []} & asked
        reason = _reason(result) if _status(result) != _COMPLETE else None
        document = result.document
        without_text = sorted(reached - text_pages(document))
        ocr_pages: list[int] = []
        if self._config.ocr and without_text and self.ocr_available():
            scanned = self._convert(True, name, content, without_text).document
            ocr_pages = sorted(set(without_text) & text_pages(scanned))
            if ocr_pages:
                kept = reached - set(ocr_pages)
                document = joined([(document, kept), (scanned, set(ocr_pages))], sorted(reached), concatenate)
                without_text = sorted(set(without_text) - set(ocr_pages))
        processed = reached
        if previous is not None:  # resumed: what was stored, and the pending pages reached now
            stored = import_module("docling_core.types.doc").DoclingDocument.model_validate(previous.document)
            before = set(range(1, total + 1)) - set(pending)
            document = joined([(stored, before), (document, reached)], list(range(1, total + 1)), concatenate)
            processed = before | reached
            without_text = sorted(set(previous.coverage.without_text) | set(without_text))
        coverage = PageCoverage(
            total=total,
            processed=len(processed),
            pending=sorted(asked - reached),
            without_text=without_text,
            reason=reason,
        )
        output: Mapping[str, object] = document.export_to_dict()
        return ParsedOutput(output, coverage, ocr_pages)
