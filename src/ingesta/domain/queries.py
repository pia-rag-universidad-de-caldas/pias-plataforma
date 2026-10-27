"""API queries on the chunkable files: filter and paginate.

The chunkable ones are those with the CHUNKABLE category in archivos_categorias, that is, what the last
reorganization left in vigentes/ (nothing is reclassified: the API only reads the memory).
"""

from ingesta.models import FileFilter, FilePage, FileRecord

from .naming import Naming


class Queries:
    """Only static methods."""

    @staticmethod
    def normalized_types(types: list[str]) -> frozenset[str]:
        """The types as the memory stores them (lowercase and equivalents: JPEG -> jpg)."""
        return frozenset(Naming.file_type(f"x.{t.lstrip('.')}") for t in types)

    @staticmethod
    def matches(record: FileRecord, filter_: FileFilter) -> bool:
        return (
            (not filter_.types or record.tipo in filter_.types)
            and (filter_.year is None or record.anio == filter_.year)
            and (filter_.month is None or record.mes_num == filter_.month)
            and (filter_.week is None or record.semana == filter_.week)
            and (filter_.code is None or record.codigo == filter_.code)
        )

    @staticmethod
    def is_safe(path: str) -> bool:
        """Relative and without a ".." segment: only those are ever served, even if the memory had another."""
        return not path.startswith("/") and ".." not in path.split("/")

    @staticmethod
    def chunkable_with_hash(records: list[FileRecord], chunkable_origins: set[str]) -> FileRecord | None:
        """The chunkable file among those with one content (at most one is: hash duplicates aren't chunkable), if
        its paths are safe."""
        found = next((r for r in records if r.origen in chunkable_origins), None)
        if found is None or not Queries.is_safe(found.origen) or not Queries.is_safe(found.destino):
            return None
        return found

    @staticmethod
    def chunkable(records: list[FileRecord], chunkable_origins: set[str], filter_: FileFilter) -> list[FileRecord]:
        """Main function: the chunkable ones that meet the filter, ordered by `origen` (stable across pages)."""
        selected = (r for r in records if r.origen in chunkable_origins and Queries.matches(r, filter_))
        return sorted(selected, key=lambda r: r.origen)

    @staticmethod
    def paginate(records: list[FileRecord], page: int, per_page: int) -> FilePage:
        """`page` from 1; a page past the last one comes out empty."""
        start = (page - 1) * per_page
        return FilePage(
            page=page,
            per_page=per_page,
            total=len(records),
            pages=-(-len(records) // per_page),
            files=records[start : start + per_page],
        )
