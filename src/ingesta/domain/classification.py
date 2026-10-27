"""Classification of the ingest: which categories each already registered file has.

Each category is evaluated separately, so a file can have several:
- EMPTY          — weighs less than ALMOST_EMPTY_THRESHOLD;
- UNSUPPORTED    — type outside SUPPORTED_TYPES (pdf/doc/docx);
- INCOMPLETE     — without the year/month/week/code structure (its code isn't reliable: it doesn't compete);
- HASH_DUPLICATE — there is a newer one with the same sha256 (of each group the last modified one stays);
- CODE_DUPLICATE — it competes by code and the representative of its code is another one. The complete,
                   supported and non-empty files compete (so an empty .txt or a newer .csv don't take the current
                   status away from the PDF of their code); the representative is the newest of the ones that are
                   not HASH_DUPLICATE;
- CURRENT        — neither HASH_DUPLICATE nor CODE_DUPLICATE (it can be empty, unsupported or incomplete);
- CHUNKABLE      — CURRENT, supported and not empty: what Docling chunks.

The main one is the one with the highest priority (Category order) and decides the folder: vigentes/ has exactly
the CHUNKABLE ones. It depends on the whole corpus: a new file can displace one that was CURRENT.
"""

from collections import defaultdict
from collections.abc import Iterable
from typing import ClassVar

from ingesta.models import Category, CategoryDefinition, FileClassification, FileRecord

from .duplicates import Duplicates
from .naming import Naming

ClassificationMap = dict[str, FileClassification]  # origin -> categories

Tags = dict[str, set[Category]]  # origin -> categories found so far


class Classifier:
    """Only static methods: each step of the classification is a method and `classify` joins them."""

    PRIORITY: ClassVar[dict[Category, int]] = {c: i for i, c in enumerate(Category, 1)}

    # Stored in the `categorias` catalog of the memory: they stay as they are.
    _DESCRIPTIONS: ClassVar[dict[Category, str]] = {
        Category.EMPTY: "0 B o casi vacío (menos de UMBRAL_CASI_VACIO)",
        Category.UNSUPPORTED: "tipo que no se fragmenta (fuera de TIPOS_SOPORTADOS)",
        Category.HASH_DUPLICATE: "mismo contenido (sha256) que otro modificado después",
        Category.CODE_DUPLICATE: "mismo código que el vigente de ese código",
        Category.INCOMPLETE: "ruta sin estructura anio/mes/semana/codigo",
        Category.CHUNKABLE: "vigente, pdf/doc/docx y no vacío: lo que fragmenta Docling",
        Category.CURRENT: "ni hash duplicado ni código duplicado (puede ser vacío, extraño o incompleto)",
    }

    @staticmethod
    def category_definitions() -> list[CategoryDefinition]:
        """Content of the `categorias` catalog."""
        return [
            CategoryDefinition(c.value, Naming.folder_of(c), Classifier.PRIORITY[c], Classifier._DESCRIPTIONS[c])
            for c in Category
        ]

    # --- steps ---

    @staticmethod
    def file_tags(record: FileRecord) -> set[Category]:
        """Step 1: what is known looking only at the file (EMPTY, UNSUPPORTED, INCOMPLETE)."""
        tags = set()
        if Naming.is_empty(record.bytes):
            tags.add(Category.EMPTY)
        if not Naming.is_supported(record.tipo):
            tags.add(Category.UNSUPPORTED)
        if not record.completo or record.codigo is None:
            tags.add(Category.INCOMPLETE)
        return tags

    @staticmethod
    def hash_duplicates(records: list[FileRecord]) -> set[str]:
        """Step 2: origins that are a copy of another one with the same sha256 (HASH_DUPLICATE)."""
        return {copy.origen for group in Duplicates.group(records) for copy in group.copies}

    @staticmethod
    def code_duplicates(records: list[FileRecord], tags: Tags) -> set[str]:
        """Step 3: origins whose code already has another representative (CODE_DUPLICATE). The complete, supported
        and non-empty ones compete; the representative is the newest of the ones that are not HASH_DUPLICATE."""
        by_code: dict[str, list[FileRecord]] = defaultdict(list)
        for record in records:
            if record.codigo is not None and not tags[record.origen] - {Category.HASH_DUPLICATE}:
                by_code[record.codigo].append(record)  # complete, supported and not empty
        duplicates: set[str] = set()
        for members in by_code.values():
            competing = [r for r in members if Category.HASH_DUPLICATE not in tags[r.origen]]
            if not competing:
                continue  # the whole code is a copy of files of other codes: nobody represents it
            representative = max(competing, key=Duplicates.newness_key)
            duplicates |= {r.origen for r in members if r is not representative}
        return duplicates

    @staticmethod
    def current_tags(categories: set[Category]) -> set[Category]:
        """Step 4: CURRENT if it isn't a duplicate of any kind; also CHUNKABLE if it isn't empty or unsupported
        either."""
        if categories & {Category.HASH_DUPLICATE, Category.CODE_DUPLICATE}:
            return set()
        if categories & {Category.EMPTY, Category.UNSUPPORTED}:
            return {Category.CURRENT}
        return {Category.CURRENT, Category.CHUNKABLE}

    @staticmethod
    def principal(categories: set[Category]) -> Category:
        """Step 5: the one with the highest priority (Category order); it decides the folder."""
        return min(categories, key=Classifier.PRIORITY.__getitem__)

    # --- main function ---

    @staticmethod
    def classify(records: Iterable[FileRecord]) -> ClassificationMap:
        """Joins the steps, in order: each one uses what the previous ones found."""
        all_records = list(records)
        tags: Tags = {r.origen: Classifier.file_tags(r) for r in all_records}
        for origin in Classifier.hash_duplicates(all_records):
            tags[origin].add(Category.HASH_DUPLICATE)
        for origin in Classifier.code_duplicates(all_records, tags):
            tags[origin].add(Category.CODE_DUPLICATE)
        result: ClassificationMap = {}
        for origin, categories in tags.items():
            categories |= Classifier.current_tags(categories)
            result[origin] = FileClassification(Classifier.principal(categories), frozenset(categories))
        return result
