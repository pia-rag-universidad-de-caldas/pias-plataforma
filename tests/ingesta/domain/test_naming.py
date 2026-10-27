"""Naming: the new name, the type and the provisional folder of a file."""

from ingesta.domain import Discovery, Naming
from ingesta.models import Category


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
