"""Which academic activity (course) a PIAA is: its name and its code, read from its first chunks.

The name of a course appears once, in the header of its PIAA ("Actividad académica: PSICOLOGÍA DE LA PERCEPCIÓN",
"Nombre de la Actividad Académica:" with the value on the next line, or every label first and the values after
them), so a chunk of its evaluation or its bibliography doesn't say which course it is about, and a question that
names a course can't find it by its vector. Each chunk is embedded with this identity in front (`passage_heading`),
and the JSON keeps it (`actividad`, `codigo_actividad`) for consultas to filter by course.

Only text rules: no I/O. What can't be read is None (the chunks are embedded without a heading)."""

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

HEADER_CHUNKS = 6  # the header is in the first chunks of a document
MAX_NAME = 120  # characters of a name: what is longer isn't a name
NEAR = 6  # lines after a label where its value may be (the labels may come first and the values after them)
HEADING_CHARS = 160  # the most a heading takes in front of a chunk (~40 tokens): see embeddings' limits

_NAME_LABEL = re.compile(r"(?:nombre de la\s+)?(?:actividad academica|asignatura)\s*:")
_CODE_LABEL = re.compile(r"codigo(?:\s+(?:de\s+la\s+)?actividad academica)?\s*:")
# Where a value written on the label's line ends: the next label of the header.
_NEXT_LABEL = re.compile(
    r"\s(?:codigo|numero de|version|departamento|facultad|tipo de|programas?|horas|creditos|acta)\b"
)
# A label line: it ends with a colon, or it is one of the header's labels with its value elsewhere.
_LABEL_LINE = re.compile(r":\s*$|^(?:version del|acta y fecha|academica \(piaa\))")
_CODE = re.compile(r"^(?=[A-Z0-9]*\d)[A-Z0-9]{4,12}$")  # 0100105, 616G7F, G6K0346 (never a form code: R-2680-P-DC)
_NOT_NAME = re.compile(r"^(?:n/?a|-+|_+|x|si|no|\d+[\d.,/ -]*)$")
_FILE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}-[\d.]+_")  # the upload date in front of a corpus file name
_PIAA_WORD = re.compile(r"\b(?:piaa|pregrado|posgrado|final|nuevo|version\s*\d*|v\d+)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Identity:
    name: str | None = None
    code: str | None = None

    @property
    def known(self) -> bool:
        return self.name is not None or self.code is not None


def fold(text: str) -> str:
    """Lowercase and without accents, one character for one (positions stay): ñ is n, Á is a."""
    return "".join(unicodedata.normalize("NFD", c.lower())[:1] or c for c in text)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" .:;,-_")


def _name(value: str) -> str | None:
    if "=" in value:  # a table read as triplets: "<row>, <column> = <value>"
        value = value.rsplit("=", 1)[1]
    value = _clean(re.sub(r"^#+\s*", "", value.strip()))
    if "actividad academica" in fold(value):
        return None
    if not 3 <= len(value) <= MAX_NAME or _NOT_NAME.match(fold(value)) or _CODE.match(value):
        return None
    if not re.search(r"[^\W\d_]{3}", value):  # a name has a word
        return None
    return value


def _code(value: str) -> str | None:
    value = _clean(value).upper()
    return value if _CODE.match(value) else None


def _is_label(folded: str) -> bool:
    return bool(_LABEL_LINE.search(folded)) or ("actividad academica" in folded and ":" in folded)


def _inline(line: str, folded: str, end: int) -> str:
    """The value written after a label on its own line, up to the next label."""
    rest = folded[end:]
    stop = _NEXT_LABEL.search(rest)
    return line[end : end + (stop.start() if stop else len(rest))]


def _name_labels(folded: str) -> Iterable[re.Match[str]]:
    """The name labels of a line: "Actividad académica:" alone, or after "Nombre de la", never the faculty's,
    department's or code's ("…que ofrece la Actividad Académica:", "Código actividad académica:")."""
    for found in _NAME_LABEL.finditer(folded):
        before = folded[: found.start()].rstrip()
        if found.group(0).startswith("nombre") or (
            found.group(0).startswith("actividad") and not re.search(r"(?:\bla|\bde|codigo|\bdel?)$", before)
        ):
            yield found


def _following(lines: Sequence[str], start: int) -> list[str]:
    """The values that may belong to the label in `start`: when several labels come one after the other and their
    values after them, in the same order, the label's own value first; then the rest, as far as NEAR lines."""
    first = start
    while first > 0 and lines[first - 1] and _is_label(fold(lines[first - 1])):
        first -= 1
    last = start
    while last + 1 < len(lines) and lines[last + 1] and _is_label(fold(lines[last + 1])):
        last += 1
    values = [line for line in lines[last + 1 : last + 1 + NEAR + start - first] if line and not _is_label(fold(line))]
    position = start - first
    return values[position:] + values[:position] if position < len(values) else values


def from_chunks(texts: Sequence[str]) -> Identity:
    """The name and code of the course, from the first chunks of its document."""
    lines = [line.strip() for text in texts[:HEADER_CHUNKS] for line in text.splitlines()]
    name: str | None = None
    code: str | None = None
    for index, line in enumerate(lines):
        folded = fold(line)
        if name is None:
            for found in _name_labels(folded):
                name = _name(_inline(line, folded, found.end())) or next(
                    (n for n in map(_name, _following(lines, index)) if n), None
                )
                if name:
                    break
        if code is None:
            for found in _CODE_LABEL.finditer(folded):
                inline = _inline(line, folded, found.end()).split()
                code = _code(inline[0]) if inline else None
                code = code or next((c for c in map(_code, _following(lines, index)) if c), None)
                if code:
                    break
        if name and code:
            break
    return Identity(name, code)


def from_file_name(file_name: str | None) -> str | None:
    """A name from the file's name, when it has words ("PIAA_Sistemas_Termosolares.pdf"), not only numbers."""
    if not file_name:
        return None
    stem = _FILE_PREFIX.sub("", file_name.rsplit("/", 1)[-1]).rsplit(".", 1)[0]
    words = _PIAA_WORD.sub(" ", stem.replace("_", " "))
    words = " ".join(w for w in words.split() if not _CODE.match(w.upper()) and w != "-")
    return _name(words)


def identify(texts: Sequence[str], file_name: str | None = None) -> Identity:
    """From the chunks; the name, if they don't have it, from the file's name."""
    found = from_chunks(texts)
    if found.name is None:
        return Identity(from_file_name(file_name), found.code)
    return found


def passage_heading(identity: Identity) -> str:
    """What goes in front of each chunk of the document: the course it is about ("" if unknown)."""
    if not identity.known:
        return ""
    parts = [f"Actividad académica: {identity.name}" if identity.name else "Actividad académica"]
    if identity.code:
        parts.append(f"código {identity.code}")
    return " · ".join(parts)[:HEADING_CHARS] + "\n"
