"""The fixed configuration of the parsing (feature 042), in one place. Nothing of it can be asked in a request: the
most complete parsing Docling gives, for every file. Changing a value here is raising PARSING_VERSION: every document
is then pending to be parsed again (it enters the fingerprint)."""

from dataclasses import asdict, dataclass

PARSING_VERSION = 1


@dataclass(frozen=True)
class ParsingConfig:
    # Tables: rows, columns and merged cells; the text of each cell comes from the PDF, not from the model.
    table_structure: bool = True
    table_mode: str = "accurate"  # TableFormer's mode: accurate (better merged cells) or fast
    cell_matching: bool = True
    # PDF titles with their real level (bookmarks, numbering, style): without it, Docling gives every title level 1.
    heading_hierarchy: bool = True
    # Word templates: list items numbered with Roman numerals are titles ("I." level 1, "III.1." level 2).
    roman_titles: bool = True
    # OCR only where it is needed: a second pass, full page, over the pages that have no text without it.
    ocr: bool = True
    ocr_engine: str = "rapidocr"  # with onnxruntime (the `parse` extra): reads Spanish (accents included) offline
    ocr_full_page: bool = True
    document_timeout: float = 600.0  # seconds per conversion; past it, the document is partial and resumes later
    device: str = "cpu"
    # What stays off: slow vision models that don't apply to the PIAA.
    picture_description: bool = False
    picture_classification: bool = False
    formula_enrichment: bool = False
    code_enrichment: bool = False
    chart_extraction: bool = False

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


PARSING = ParsingConfig()
