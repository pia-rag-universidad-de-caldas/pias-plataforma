"""Text tools."""

import re

# One part of the key per piece of text: (0, number, "") or (1, 0, lowercase text).
# Numbers go before text and are compared as numbers.
NaturalKey = list[tuple[int, int, str]]


def leading_number(text: str) -> int | None:
    """'11_Noviembre' -> 11; None if the text doesn't start with a number."""
    m = re.match(r"\d+", text)
    return int(m.group()) if m else None


def natural_key(text: str) -> NaturalKey:
    """Sorts '2_Feb' before '10_Oct' and 'Semana_2' before 'Semana_10'."""
    return [(0, int(t), "") if t.isdigit() else (1, 0, t.lower()) for t in re.split(r"(\d+)", text) if t]


def split_path(path: str) -> tuple[str, str]:
    """'vigentes/pdf/x.pdf' -> ('vigentes/pdf', 'x.pdf'); without a folder, ('', name)."""
    folder, _, name = path.rpartition("/")
    return folder, name


def extension(name: str) -> str:
    """Like Path.suffix: 'a.tar.gz' -> '.gz'; '.bashrc', 'a.' and 'no_dot' -> ''."""
    dot = name.rfind(".")
    return name[dot:] if 0 < dot < len(name) - 1 else ""
