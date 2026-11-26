"""ORMAdapter (feature 012): the repositories ask for and store entities (models/entities.py) with a CRUD (create, read,
search, update, delete) and transactions, without knowing SQL or the ORM. It is built from scratch (creates the tables)
or from an existing memory. The implementations live in adapters/, the only package that imports the ORM."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from enum import Enum, auto
from typing import Self, overload

from .schema import Entity, ExistingColumn, TableSpec, Value


class MemoryStoreError(Exception):
    """The memory could not store a change. Raised by the repository so the domain handles it without depending
    on the ORM or the database engine."""


class Operator(Enum):
    EQUAL = auto()
    NOT_EQUAL = auto()
    IS_NULL = auto()
    NOT_NULL = auto()
    REPEATED = auto()  # the field value appears in more than one record (ignores nulls)


@dataclass(frozen=True)
class Filter:
    """Condition on an entity field (name of the dataclass field)."""

    field: str
    operator: Operator = Operator.EQUAL
    value: Value = None  # only for EQUAL and NOT_EQUAL


class ORMAdapter(ABC):
    """CRUD on the entities of the tables it was built with (feature 012).

    Built with `from_scratch` or `from_existing`; `origin` says which one was used. Each operation is its own
    transaction, except inside `transaction()`; `create` and `update` with a list do it in a single one. Every
    database failure is raised as MemoryStoreError; an unknown field, as ValueError."""

    # --- constructors ---

    @classmethod
    @abstractmethod
    def from_scratch(cls, url: str, tables: Sequence[TableSpec]) -> Self:
        """Creates at `url` a new memory with `tables`, empty; MemoryStoreError if there already is one."""

    @classmethod
    @abstractmethod
    def from_existing(cls, url: str, tables: Sequence[TableSpec]) -> Self:
        """Opens the memory that already exists at `url`, with its records, without creating tables: rebuilds the
        ones of an old version (`TableSpec.needs_migration`). MemoryStoreError if there is no memory or if it lacks
        any of `tables`."""

    # --- CRUD ---

    @overload
    def create(self, record: Entity) -> Value: ...

    @overload
    def create(self, record: Sequence[Entity]) -> list[Value]: ...

    @abstractmethod
    def create(self, record: Entity | Sequence[Entity]) -> Value | list[Value]:
        """Stores a new entity and returns its primary key (the generated one, if the database assigns it). With a
        list it stores all of them in a single transaction and returns their keys in the same order."""

    @abstractmethod
    def read[E](self, entity: type[E], *key: Value) -> E | None:
        """The record with that primary key (one value per key column, in table order), or None."""

    @abstractmethod
    def search[E](self, entity: type[E], filters: Sequence[Filter] = (), order: Sequence[str] = ()) -> list[E]:
        """Records that meet all the filters, ordered by the `order` fields."""

    @abstractmethod
    def update(self, record: Entity | Sequence[Entity]) -> None:
        """Rewrites with all its fields the entity's row, looked up by its primary key. With a list it rewrites all
        of them in a single transaction."""

    @abstractmethod
    def delete(self, entity: type[object], filters: Sequence[Filter]) -> None:
        """Deletes the records that meet all the filters; without filters it is a ValueError (it would empty the
        table)."""

    @abstractmethod
    def transaction(self) -> AbstractContextManager[None]:
        """Groups the operations of the `with` block in a single transaction: they are all committed on exit or, if
        one fails, all rolled back. Nested, it joins the one already open."""

    @abstractmethod
    def close(self) -> None:
        """Releases the database connections."""


Row = dict[str, Value]  # {field: value} of a record, as the converter reads or writes it


class SQLConverter(ABC):
    """Talks to an SQL database through a concrete ORM or driver (feature 012). SQLORMAdapter builds the CRUD on top
    of this interface without knowing the ORM: the converter is the only one that imports it.

    `open` must be called before anything else (except `exists` and `visible_url`) and `register` before operating
    on an entity. Each operation is its own transaction, except inside `transaction()`. Every database failure is
    raised as MemoryStoreError; an unknown field, as ValueError."""

    # --- connection ---

    @abstractmethod
    def exists(self, url: str) -> bool:
        """Whether at `url` there already is a database with at least one table. Creates nothing (with SQLite, not
        even the file)."""

    @abstractmethod
    def open(self, url: str) -> None:
        """Connects to `url`; with SQLite it creates the file's folder if missing."""

    @abstractmethod
    def close(self) -> None:
        """Releases the database connections."""

    @abstractmethod
    def visible_url(self, url: str) -> str:
        """The URL to show on the console, without password."""

    @abstractmethod
    def transaction(self) -> AbstractContextManager[None]:
        """Same as ORMAdapter.transaction: all the operations of the block are committed together or none."""

    # --- schema ---

    @abstractmethod
    def register(self, tables: Sequence[TableSpec]) -> None:
        """Translates the tables to the ORM and associates each entity with its table, without touching the
        database."""

    @abstractmethod
    def create_tables(self, tables: Sequence[TableSpec]) -> None:
        """Creates the (already registered) tables in the database, with their indexes."""

    @abstractmethod
    def columns(self, table: str) -> list[ExistingColumn] | None:
        """Columns the table has today in the database; None if it doesn't exist."""

    @abstractmethod
    def rebuild(self, table: TableSpec) -> None:
        """Rebuilds the (already registered) table with its current definition keeping its rows (for changes that
        ALTER doesn't support in every engine, like removing a NOT NULL)."""

    # --- registered entities ---

    @abstractmethod
    def fields(self, entity: type[object]) -> tuple[str, ...]:
        """Fields of the entity, in dataclass order; ValueError if it isn't registered."""

    @abstractmethod
    def primary_key(self, entity: type[object]) -> tuple[str, ...]:
        """Primary key fields, in table order."""

    # --- data ---

    @abstractmethod
    def insert(self, entity: type[object], row: Row) -> Value:
        """Inserts the row and returns its primary key (the generated one, if the row doesn't bring it)."""

    @abstractmethod
    def select(self, entity: type[object], filters: Sequence[Filter], order: Sequence[str]) -> list[Row]:
        """Rows (all the fields) that meet all the filters, ordered by the `order` fields."""

    @abstractmethod
    def update(self, entity: type[object], filters: Sequence[Filter], row: Row) -> None:
        """Puts the values of `row` in the records that meet all the filters."""

    @abstractmethod
    def delete(self, entity: type[object], filters: Sequence[Filter]) -> None:
        """Deletes the records that meet all the filters."""
