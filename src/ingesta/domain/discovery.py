"""Discovery rules: which structure each base/ file has and in which order it is processed."""

from typing import ClassVar

from ingesta.config import LEVELS
from ingesta.models import FileReader, OrganizationPlan, SourceFile
from ingesta.utils import NaturalKey, natural_key

# (incomplete, unknown year, year, next folders, name)
ChronologicalKey = tuple[bool, bool, int, list[NaturalKey], NaturalKey]


class Discovery:
    """Only static methods: the discovery rules under one name."""

    _FIELDS: ClassVar[tuple[str, ...]] = ("year", "month", "week", "code")  # SourceFile fields, in order

    @staticmethod
    def is_hidden(name: str) -> bool:
        """System or Office files (.DS_Store, .~lock...) that are not documents."""
        return name.startswith(".")

    @staticmethod
    def read_structure(path: str, size: int) -> SourceFile:
        """Complete if it is <year>/<month>/<week>/<code>/<file> with a numeric year.

        Otherwise, year/month/week/code are filled by position as far as the folders go, but only when the first
        one is a year; otherwise it can't be known.
        """
        parts = tuple(path.split("/"))
        folders, name = parts[:-1], parts[-1]
        starts_with_year = bool(folders) and folders[0].isdigit()
        # strict=False: an incomplete one can have fewer folders than fields (or more).
        fields = dict(zip(Discovery._FIELDS, folders, strict=False)) if starts_with_year else {}
        complete = len(parts) == LEVELS and starts_with_year
        return SourceFile(path, folders, name, complete, size, **fields)

    @staticmethod
    def chronological_key(file: SourceFile) -> ChronologicalKey:
        """First the complete ones, from the oldest year to the newest; then the incomplete ones (also by year,
        and the ones with an unknown year at the end)."""
        return (
            not file.complete,
            file.year is None,
            int(file.year) if file.year else 0,
            [natural_key(f) for f in (file.folders[1:] if file.year else file.folders)],
            natural_key(file.name),
        )

    @staticmethod
    def discover(base: FileReader) -> tuple[list[SourceFile], list[str]]:
        """Returns (files in processing order, paths of the ignored hidden files)."""
        found: list[SourceFile] = []
        hidden: list[str] = []
        for info in base.list_files():
            if Discovery.is_hidden(info.path.rpartition("/")[2]):
                hidden.append(info.path)
                continue
            found.append(Discovery.read_structure(info.path, info.bytes))
        found.sort(key=Discovery.chronological_key)
        return found, hidden

    @staticmethod
    def plan(base: FileReader, processed: set[str]) -> OrganizationPlan:
        """A file is new if its path in base/ is not in the memory."""
        found, hidden = Discovery.discover(base)
        new = [f for f in found if f.path not in processed]
        return OrganizationPlan(found, new, hidden)
