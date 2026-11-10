"""DoclingParser (feature 042) with Docling for real, on documents the test generates: text pages, a scanned page that
only OCR reads, a blank page, a resumed partial one, a Word document and the previews of feature 048."""

import io
from pathlib import Path

import pytest

from parsing.adapters import DoclingParser, joined, text_pages
from parsing.domain import preview
from parsing.models import PageCoverage, ParseError, ParseStatus, StoredParse


def pdf(*pages: str) -> bytes:
    """A PDF with one line of text per page; an empty text is a blank page."""
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode()]
    font = 3 + 2 * len(pages)
    for i, text in enumerate(pages):
        content = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode() if text else b""
        resources = f"<< /Font << /F1 {font} 0 R >> >>"
        page = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents {4 + 2 * i} 0 R /Resources {resources} >>"
        )
        objects += [page.encode(), b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content)]
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    body, offsets = b"%PDF-1.4\n", []
    for number, obj in enumerate(objects, 1):
        offsets.append(len(body))
        body += b"%d 0 obj\n%s\nendobj\n" % (number, obj)
    table_at = len(body)
    body += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    body += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    return body + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, table_at)


def with_scanned_page(content: bytes, text: str) -> bytes:
    """`content` plus a page that is only an image of `text` (no text layer: what a scanner gives)."""
    image = pytest.importorskip("PIL.Image")
    draw = pytest.importorskip("PIL.ImageDraw")
    fonts = pytest.importorskip("PIL.ImageFont")
    pdfium = pytest.importorskip("pypdfium2")
    picture = image.new("RGB", (1275, 1650), "white")
    try:
        font = fonts.truetype("DejaVuSans.ttf", 44)
    except OSError:
        font = fonts.load_default(size=44)
    draw.Draw(picture).text((120, 200), text, fill="black", font=font)
    scanned = io.BytesIO()
    picture.save(scanned, format="PDF", resolution=150)
    document = pdfium.PdfDocument(content)
    document.import_pages(pdfium.PdfDocument(scanned.getvalue()))
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


@pytest.fixture(scope="module")
def parser() -> DoclingParser:
    pytest.importorskip("docling")
    return DoclingParser()


@pytest.fixture
def layout_models() -> None:
    """The PDF pipeline needs Docling's layout and table models: they aren't downloaded for a test."""
    if not (Path.home() / ".cache/huggingface/hub/models--docling-project--docling-layout-heron").is_dir():
        pytest.skip("Docling's layout models aren't in the cache")


def texts(document: object) -> list[tuple[int, str]]:
    doc = pytest.importorskip("docling_core.types.doc").DoclingDocument.model_validate(document)
    return [(item.prov[0].page_no, item.text) for item, _ in doc.iterate_items() if getattr(item, "text", "")]


@pytest.mark.docling
@pytest.mark.integration
def test_scenario_a_scanned_page_is_read_with_ocr_and_a_blank_one_is_reported(
    parser: DoclingParser, layout_models: None
) -> None:
    if not parser.ocr_available():
        pytest.skip("the OCR engine isn't installed (uv sync --extra parse)")
    content = with_scanned_page(pdf("Primera pagina del documento", ""), "Tercera pagina escaneada")
    found = parser.parse("a.pdf", content)
    assert found.ocr_pages == [3]
    assert found.coverage == PageCoverage(total=3, processed=3, without_text=[2])
    pages = texts(found.document)
    assert pages[0] == (1, "Primera pagina del documento") and pages[-1][0] == 3
    assert "escaneada" in pages[-1][1]


@pytest.mark.docling
@pytest.mark.integration
def test_scenario_a_partial_one_resumes_only_its_pending_pages(parser: DoclingParser, layout_models: None) -> None:
    content = pdf("Primera pagina del documento", "Segunda pagina del documento")
    first = parser.parse("a.pdf", pdf("Primera pagina del documento"))
    previous = StoredParse(first.document, PageCoverage(2, 1, [2]), ParseStatus.PARTIAL, "f1")
    found = parser.parse("a.pdf", content, previous)
    assert (found.coverage.processed, found.coverage.pending) == (2, [])
    assert [page for page, _ in texts(found.document)] == [1, 2]


@pytest.mark.docling
def test_a_word_document_has_no_pages_nor_ocr(parser: DoclingParser) -> None:
    word = pytest.importorskip("docx").Document()
    word.add_heading("Objetivo", level=1)
    word.add_paragraph("Un párrafo de la sección.")
    buffer = io.BytesIO()
    word.save(buffer)
    found = parser.parse("a.docx", buffer.getvalue())
    assert found.coverage == PageCoverage() and found.ocr_pages == []
    doc = pytest.importorskip("docling_core.types.doc").DoclingDocument.model_validate(found.document)
    assert [str(item.label.value) for item, _ in doc.iterate_items()] == ["section_header", "text"]


@pytest.mark.docling
def test_a_file_that_isnt_what_it_says_is_the_documents_fault(parser: DoclingParser) -> None:
    with pytest.raises(ParseError):
        parser.parse("a.docx", b"esto no es un word")


def test_the_parts_of_a_document_are_joined_by_page() -> None:
    doc = pytest.importorskip("docling_core.types.doc")

    def one(page: int, text: str) -> object:
        document = doc.DoclingDocument(name="x")
        document.add_page(page_no=page, size=doc.Size(width=10, height=10))
        prov = doc.ProvenanceItem(page_no=page, bbox=doc.BoundingBox(l=0, t=0, r=1, b=1), charspan=(0, len(text)))
        document.add_text(doc.DocItemLabel.TEXT, text, prov=prov)
        return document

    merged = joined([(one(2, "dos"), {2}), (one(1, "uno"), {1})], [1, 2], doc.DoclingDocument.concatenate)
    assert [(item.prov[0].page_no, item.text) for item, _ in merged.iterate_items()] == [(1, "uno"), (2, "dos")]
    assert text_pages(merged) == {1, 2}


@pytest.mark.docling
def test_a_word_document_is_previewed_by_sections(parser: DoclingParser) -> None:
    word = pytest.importorskip("docx").Document()
    word.add_heading("Evaluación", level=1)
    word.add_paragraph("Dos parciales y un proyecto.")
    table = word.add_table(rows=2, cols=2)
    for (row, column), value in {(0, 0): "Parcial", (0, 1): "30 %", (1, 0): "Proyecto", (1, 1): "40 %"}.items():
        table.cell(row, column).text = value
    word.add_heading("Bibliografía", level=1)
    word.add_paragraph("Un libro.")
    buffer = io.BytesIO()
    word.save(buffer)
    output = parser.preview("plan.docx", buffer.getvalue(), 30)
    found = preview("plan.docx", output.document, output.coverage, 30)
    assert [(s.headings, s.text) for s in found.sections] == [
        (["Evaluación"], "Dos parciales y un proyecto.\nParcial | 30 %\nProyecto | 40 %"),
        (["Bibliografía"], "Un libro."),
    ]
    assert not found.truncated


@pytest.mark.docling
def test_of_a_pdf_only_the_first_pages_are_previewed(parser: DoclingParser, layout_models: None) -> None:
    output = parser.preview("a.pdf", pdf("Primera pagina", "Segunda pagina", "Tercera pagina"), 2)
    found = preview("a.pdf", output.document, output.coverage, 2)
    assert (found.pages, found.truncated) == (3, True)
    assert "Primera pagina" in found.text and "Segunda pagina" in found.text and "Tercera" not in found.text
