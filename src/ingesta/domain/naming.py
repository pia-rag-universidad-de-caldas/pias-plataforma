"""Naming rules: which folder each file goes to and how it is renamed. Paths are text with "/"."""

from typing import ClassVar

from ingesta.config import (
    ALMOST_EMPTY_THRESHOLD,
    CODE_DUPLICATES_FOLDER,
    CURRENT_FOLDER,
    EMPTY_FOLDER,
    EQUIVALENT_EXTENSIONS,
    HASH_DUPLICATES_FOLDER,
    INCOMPLETE_FOLDER,
    NO_EXTENSION,
    SUPPORTED_TYPES,
    UNSUPPORTED_FOLDER,
)
from ingesta.models import Category, SourceFile
from ingesta.utils import extension


class Naming:
    """Only static methods: the naming and folder rules under one name."""

    _FOLDERS: ClassVar[dict[Category, str]] = {
        Category.EMPTY: EMPTY_FOLDER,
        Category.UNSUPPORTED: UNSUPPORTED_FOLDER,
        Category.HASH_DUPLICATE: HASH_DUPLICATES_FOLDER,
        Category.CODE_DUPLICATE: CODE_DUPLICATES_FOLDER,
        Category.CHUNKABLE: CURRENT_FOLDER,  # vigentes/ = the chunkable ones
        # Never the main one: a current file is also chunkable, empty, unsupported or incomplete.
        Category.CURRENT: CURRENT_FOLDER,
        Category.INCOMPLETE: INCOMPLETE_FOLDER,
    }

    @staticmethod
    def file_type(name: str) -> str:
        """Lowercase extension, unifying equivalents (jpeg -> jpg)."""
        suffix = extension(name).lower().lstrip(".")
        return EQUIVALENT_EXTENSIONS.get(suffix, suffix) or NO_EXTENSION

    @staticmethod
    def new_name(file: SourceFile) -> str:
        """The folders as far as the hierarchy goes, joined with '-', and the original name.

        Complete:   2024/11_Nov/Semana_04/671047/doc.pdf -> 2024-11_Nov-Semana_04-671047-doc.pdf
        Incomplete: 2024/suelto/x.txt                    -> 2024-suelto-x.txt
        """
        return "-".join((*file.folders, file.name))

    @staticmethod
    def is_empty(size: int) -> bool:
        """Empty (0 B) or almost empty (less than ALMOST_EMPTY_THRESHOLD): it brings no content."""
        return size < ALMOST_EMPTY_THRESHOLD

    @staticmethod
    def is_supported(file_type: str) -> bool:
        """Type that gets chunked (SUPPORTED_TYPES); the rest is an unsupported file."""
        return file_type in SUPPORTED_TYPES

    @staticmethod
    def folder_of(category: Category) -> str:
        return Naming._FOLDERS[category]

    @staticmethod
    def folder_for(category: Category, file_type: str) -> str:
        """Relative to ingesta/: <folder of the main category>/<type>. It is the only folder rule."""
        return f"{Naming._FOLDERS[category]}/{file_type}"

    @staticmethod
    def provisional_category(file: SourceFile) -> Category:
        """Category of a new file before knowing its hash and comparing it with the corpus; Organization.relocate
        fixes it in the same run (see domain.classification)."""
        if Naming.is_empty(file.bytes):
            return Category.EMPTY
        if not Naming.is_supported(Naming.file_type(file.name)):
            return Category.UNSUPPORTED
        return Category.CHUNKABLE if file.complete else Category.INCOMPLETE

    @staticmethod
    def target_folder(file: SourceFile) -> str:
        return Naming.folder_for(Naming.provisional_category(file), Naming.file_type(file.name))
