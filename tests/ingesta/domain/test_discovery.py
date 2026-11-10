"""Discovery: the structure of each file of base/, the hidden ones and the processing order."""

from ingesta.domain import Discovery


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
