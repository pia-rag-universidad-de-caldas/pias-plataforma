"""Classification of the corpus (Classifier): which categories each file has and which one decides its folder."""

from ingesta.domain import Classifier
from ingesta.models import Category, FileRecord

KB = 1024


def record(
    origin: str,
    sha: str | None,
    modified: str = "2024-01-01T00:00:00",
    code: str | None = "020055",
    file_type: str = "pdf",
    size: int = 10 * KB,
    complete: bool = True,
) -> FileRecord:
    return FileRecord(
        origen=origin,
        destino=f"x/{origin}",
        anio=2024 if complete else None,
        mes="01_Enero" if complete else None,
        mes_num=1 if complete else None,
        semana="Semana_01" if complete else None,
        codigo=code,
        nombre=origin.rpartition("/")[2],
        tipo=file_type,
        bytes=size,
        modificado=modified,
        procesado_en="2024-02-01T00:00:00",
        accion="copiado",
        sha256=sha,
        completo=complete,
    )


def main(*records: FileRecord) -> dict[str, Category]:
    return {origin: c.main for origin, c in Classifier.classify(records).items()}


def categories(*records: FileRecord) -> dict[str, set[Category]]:
    return {origin: set(c.categories) for origin, c in Classifier.classify(records).items()}


def test_a_lone_pdf_is_current_and_chunkable() -> None:
    assert categories(record("a.pdf", "h1")) == {"a.pdf": {Category.CURRENT, Category.CHUNKABLE}}
    assert main(record("a.pdf", "h1")) == {"a.pdf": Category.CHUNKABLE}


def test_of_one_code_the_newest_stays_chunkable() -> None:
    old = record("old.pdf", "h1", "2024-01-01T00:00:00")
    new = record("new.docx", "h2", "2024-03-01T00:00:00", file_type="docx")
    assert main(old, new) == {"old.pdf": Category.CODE_DUPLICATE, "new.docx": Category.CHUNKABLE}


def test_of_one_content_the_last_modified_stays_and_hash_beats_code() -> None:
    copy = record("a/copy.pdf", "same", "2024-01-01T00:00:00", code="111111")
    original = record("b/original.pdf", "same", "2024-05-01T00:00:00", code="222222")
    found = categories(copy, original)
    assert found["a/copy.pdf"] == {Category.HASH_DUPLICATE}
    assert found["b/original.pdf"] == {Category.CURRENT, Category.CHUNKABLE}


def test_an_empty_or_unsupported_newer_file_doesnt_displace_the_pdf() -> None:
    pdf = record("piaa.pdf", "h1", "2024-01-01T00:00:00")
    empty = record("empty.pdf", "h2", "2024-06-01T00:00:00", size=10)
    csv = record("notes.csv", "h3", "2024-06-01T00:00:00", file_type="csv")
    assert main(pdf, empty, csv) == {
        "piaa.pdf": Category.CHUNKABLE,
        "empty.pdf": Category.EMPTY,  # also CURRENT: it is no duplicate
        "notes.csv": Category.UNSUPPORTED,
    }
    assert categories(pdf, empty, csv)["empty.pdf"] == {Category.EMPTY, Category.CURRENT}


def test_a_code_made_only_of_copies_has_no_representative() -> None:
    elsewhere = record("other/orig.pdf", "same", "2024-09-01T00:00:00", code="999999")
    copy = record("mine/copy.pdf", "same", "2024-01-01T00:00:00", code="020055")
    assert categories(elsewhere, copy)["mine/copy.pdf"] == {Category.HASH_DUPLICATE}


def test_an_incomplete_file_doesnt_compete_by_code() -> None:
    complete = record("2024/a.pdf", "h1", "2024-01-01T00:00:00")
    loose = record("loose.pdf", "h2", "2024-09-01T00:00:00", complete=False)
    assert main(complete, loose) == {"2024/a.pdf": Category.CHUNKABLE, "loose.pdf": Category.INCOMPLETE}


def test_an_incomplete_supported_file_is_also_chunkable() -> None:
    """Current behaviour (031): INCOMPLETE is its main category (folder formato_incompleto/) but it also gets CHUNKABLE,
    and GET /ingesta/data serves every file with CHUNKABLE, main or not. Documented here, not decided: see the 031
    report."""
    loose = record("loose.pdf", "h2", complete=False, code=None)
    assert categories(loose)["loose.pdf"] == {Category.INCOMPLETE, Category.CURRENT, Category.CHUNKABLE}


def test_the_catalog_has_every_category_with_its_folder_and_priority() -> None:
    definitions = {d.nombre: (d.carpeta, d.prioridad) for d in Classifier.category_definitions()}
    assert definitions["vacio"] == ("vacios", 1)
    assert definitions["apto_chunking"] == ("vigentes", 6)
    assert len(definitions) == len(Category)
