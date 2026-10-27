"""Structure, order and naming of the files of base/ (Discovery, Naming)."""

from ingesta.domain import Discovery, Naming
from ingesta.models import Category


def test_complete_needs_five_levels_and_a_numeric_year() -> None:
    complete = Discovery.read_structure("2024/11_Nov/Semana_04/671047/doc.pdf", 10)
    assert complete.complete and (complete.year, complete.code) == ("2024", "671047")
    assert not Discovery.read_structure("2024/suelto/x.txt", 10).complete
    word = Discovery.read_structure("varios/11/Semana_04/671047/doc.pdf", 10)
    assert not word.complete and word.year is None and word.code is None


def test_hidden_files_are_names_starting_with_a_dot() -> None:
    assert Discovery.is_hidden(".DS_Store") and Discovery.is_hidden(".~lock.a.docx#")
    assert not Discovery.is_hidden("a.pdf")


def test_complete_first_then_incomplete_and_unknown_years_last() -> None:
    paths = ["x/y.pdf", "2024/b.pdf", "2023/10/S/1/a.pdf", "2023/2/S/1/a.pdf", "2022/1/S/1/a.pdf"]
    files = sorted((Discovery.read_structure(p, 1) for p in paths), key=Discovery.chronological_key)
    assert [f.path for f in files] == [
        "2022/1/S/1/a.pdf",
        "2023/2/S/1/a.pdf",
        "2023/10/S/1/a.pdf",
        "2024/b.pdf",
        "x/y.pdf",
    ]


def test_new_name_flattens_the_folders() -> None:
    file = Discovery.read_structure("2024/11_Nov/Semana_04/671047/doc.pdf", 10)
    assert Naming.new_name(file) == "2024-11_Nov-Semana_04-671047-doc.pdf"


def test_file_type_is_lowercase_with_equivalences() -> None:
    assert Naming.file_type("A.JPEG") == "jpg"
    assert Naming.file_type("README") == "sin_extension"


def test_provisional_folder_of_a_new_file() -> None:
    assert Naming.target_folder(Discovery.read_structure("2024/1/S/1/a.pdf", 5000)) == "vigentes/pdf"
    assert Naming.target_folder(Discovery.read_structure("2024/1/S/1/a.pdf", 10)) == "vacios/pdf"
    assert Naming.target_folder(Discovery.read_structure("2024/1/S/1/a.csv", 5000)) == "archivos_extranios/csv"
    assert Naming.target_folder(Discovery.read_structure("a.pdf", 5000)) == "formato_incompleto/pdf"
    assert Naming.folder_for(Category.HASH_DUPLICATE, "pdf") == "hash_duplicados/pdf"
