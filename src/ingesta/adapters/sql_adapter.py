"""Implementation of models.ORMAdapter on an SQL database, without knowing the ORM.

It sets the CRUD rules (validate the memory, decide migrations, build entities, one or several in a transaction)
and delegates everything that touches the database to the SQLConverter it receives when built (by default
SqlAlchemyConverter, the only one that imports SQLAlchemy).
"""

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from typing import Self, overload

from ingesta.models import (
    Entity,
    Filter,
    MemoryStoreError,
    Operator,
    ORMAdapter,
    SQLConverter,
    TableSpec,
    Value,
)

from .sqlalchemy_converter import SqlAlchemyConverter


class SQLORMAdapter(ORMAdapter):
    def __init__(self, converter: SQLConverter) -> None:
        """Don't use directly: build with `from_scratch` or `from_existing`, which validate the memory."""
        self._converter = converter

    # --- constructors ---

    @classmethod
    def from_scratch(cls, url: str, tables: Sequence[TableSpec], converter: SQLConverter | None = None) -> Self:
        converter = converter or SqlAlchemyConverter()
        if converter.exists(url):
            raise MemoryStoreError(f"there already is a memory at {converter.visible_url(url)}")
        converter.open(url)
        try:
            converter.register(tables)
            with converter.transaction():
                converter.create_tables(tables)
        except BaseException:
            converter.close()
            raise
        return cls(converter)

    @classmethod
    def from_existing(cls, url: str, tables: Sequence[TableSpec], converter: SQLConverter | None = None) -> Self:
        converter = converter or SqlAlchemyConverter()
        if not converter.exists(url):
            raise MemoryStoreError(f"the memory {converter.visible_url(url)} doesn't exist")
        converter.open(url)
        try:
            converter.register(tables)
            # A single transaction: if a migration fails halfway, the memory stays as it was.
            with converter.transaction():
                for table in tables:
                    existing = converter.columns(table.name)
                    if existing is None and table.created_if_missing:
                        converter.create_tables((table,))
                        continue
                    if existing is None:
                        raise MemoryStoreError(
                            f"the memory {converter.visible_url(url)} is missing the table {table.name}"
                        )
                    if table.needs_migration is not None and table.needs_migration(existing):
                        converter.rebuild(table)  # old version: rebuilt keeping its rows
        except BaseException:
            converter.close()
            raise
        return cls(converter)

    # --- CRUD: each call is a transaction, except inside `transaction()` ---

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._converter.transaction():
            yield

    @overload
    def create(self, record: Entity) -> Value: ...

    @overload
    def create(self, record: Sequence[Entity]) -> list[Value]: ...

    def create(self, record: Entity | Sequence[Entity]) -> Value | list[Value]:
        if isinstance(record, Sequence):
            with self.transaction():
                return [self._create_one(r) for r in record]
        return self._create_one(record)

    def _create_one(self, record: object) -> Value:
        entity = type(record)
        row = {c: getattr(record, c) for c in self._converter.fields(entity)}
        key = self._converter.primary_key(entity)[0]
        if row[key] is None:
            del row[key]  # assigned by the database
        return self._converter.insert(entity, row)

    def read[E](self, entity: type[E], *key: Value) -> E | None:
        keys = self._converter.primary_key(entity)
        if len(key) != len(keys):
            raise ValueError(f"{entity.__name__} has {len(keys)} key fields and {len(key)} values were given")
        found = self.search(entity, [Filter(c, Operator.EQUAL, v) for c, v in zip(keys, key, strict=True)])
        return found[0] if found else None

    def search[E](self, entity: type[E], filters: Sequence[Filter] = (), order: Sequence[str] = ()) -> list[E]:
        build: Callable[..., E] = entity
        return [build(**row) for row in self._converter.select(entity, filters, order)]

    def update(self, record: Entity | Sequence[Entity]) -> None:
        if isinstance(record, Sequence):
            with self.transaction():
                for r in record:
                    self._rewrite(r)
        else:
            self._rewrite(record)

    def _rewrite(self, record: object) -> None:
        """The row with the primary key of `record` gets all its fields."""
        entity = type(record)
        keys = self._converter.primary_key(entity)
        filters = [Filter(c, Operator.EQUAL, getattr(record, c)) for c in keys]
        row = {c: getattr(record, c) for c in self._converter.fields(entity) if c not in keys}
        if row:
            self._converter.update(entity, filters, row)

    def delete(self, entity: type[object], filters: Sequence[Filter]) -> None:
        if not filters:
            raise ValueError("deleting without filters would empty the whole table")
        self._converter.delete(entity, filters)

    def close(self) -> None:
        self._converter.close()


def create_adapter(url: str, tables: Sequence[TableSpec], converter: SQLConverter | None = None) -> SQLORMAdapter:
    """The memory at `url`: the existing one with its records or, if there is none, a new one from scratch."""
    converter = converter or SqlAlchemyConverter()
    if converter.exists(url):
        return SQLORMAdapter.from_existing(url, tables, converter)
    return SQLORMAdapter.from_scratch(url, tables, converter)


def visible_url(url: str) -> str:
    """The URL to show on the console, without password (shortcut for the CLI)."""
    return SqlAlchemyConverter().visible_url(url)
