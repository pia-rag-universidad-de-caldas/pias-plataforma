"""`categorias` catalog and `archivos_categorias` relationship (implements models.CategoryRepository)."""

from collections.abc import Iterable

from ingesta.models import CategoryDefinition, FileCategory, Filter, ORMAdapter


class DbCategoryRepository:
    def __init__(self, data: ORMAdapter) -> None:
        self._data = data

    def sync_catalog(self, definitions: Iterable[CategoryDefinition]) -> None:
        existing = {d.nombre: d for d in self._data.search(CategoryDefinition)}
        definitions = list(definitions)
        with self._data.transaction():
            self._data.create([d for d in definitions if d.nombre not in existing])
            self._data.update([d for d in definitions if d.nombre in existing and existing[d.nombre] != d])

    def all(self) -> list[FileCategory]:
        return self._data.search(FileCategory, order=("origen", "categoria"))

    def add(self, rows: Iterable[FileCategory]) -> None:
        self._data.create(list(rows))

    def remove(self, pairs: Iterable[tuple[str, str]]) -> None:
        with self._data.transaction():
            for origin, category in pairs:
                self._data.delete(FileCategory, (Filter("origen", value=origin), Filter("categoria", value=category)))

    def mark_main(self, rows: Iterable[FileCategory]) -> None:
        self._data.update(list(rows))  # each row already brings its new `principal`

    def origins_with(self, category: str) -> set[str]:
        return {c.origen for c in self._data.search(FileCategory, (Filter("categoria", value=category),))}
