"""Contract with the memory, engine-agnostic (feature 008).

- Tables: which columns each one has, without SQL or ORM syntax. The project's ones are described in tables/ and
  the adapter (adapters/) translates them to its engine.
- ORMAdapter (feature 012): the repositories ask for and store entities (models/entities.py) with a CRUD (create,
  read, search, update, delete) and transactions, without knowing SQL or the ORM. It is built from scratch (creates
  the tables) or from an existing memory. The implementations live in adapters/, the only package that imports the
  ORM.
- FileAdapter (feature 013): read and write files under a root, with relative paths as text. The implementation
  lives in adapters/, the only package that uses pathlib, shutil, os and stat.
- Repositories: the only thing the domain knows about the memory.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import AbstractContextManager
from dataclasses import Field, dataclass
from enum import Enum, auto
from typing import ClassVar, Protocol, Self, overload

from .concepts import FileMetadata
from .entities import CategoryDefinition, FileCategory, FileRecord, Run

Value = str | int | bool | None  # simple value stored in a column


class Entity(Protocol):
    """A row of a table: any dataclass of models/entities.py."""

    __dataclass_fields__: ClassVar[dict[str, Field[object]]]


class MemoryStoreError(Exception):
    """The memory could not store a change. Raised by the repository so the domain handles it without depending
    on the ORM or the database engine."""


class FileError(Exception):
    """File system failure (doesn't exist, no permission, disk full...). Raised by the FileAdapter so the domain
    handles it without depending on os or pathlib."""


# --- tables ---


class DataType(Enum):
    TEXT = auto()
    INTEGER = auto()
    BOOLEAN = auto()


@dataclass(frozen=True)
class ColumnSpec:
    name: str  # same as the entity field
    type: DataType
    nullable: bool = False
    key: bool = False  # primary key
    autoincrement: bool = False  # the database assigns the value and never reuses it
    index: bool = False
    default: Value = None  # default value in the database (None: no default)
    reference: str | None = None  # foreign key, "table.column"


@dataclass(frozen=True)
class ExistingColumn:
    """Column as it is today in the database (to decide migrations)."""

    name: str
    nullable: bool


@dataclass(frozen=True)
class TableSpec:
    """A table and the entity (dataclass of models/entities.py) it stores: one field per column, with the same
    name. `needs_migration` says, given the columns it has today in the database, whether it is an old version that
    must be rebuilt when the memory is opened."""

    name: str
    entity: type[object]
    columns: tuple[ColumnSpec, ...]
    needs_migration: Callable[[list[ExistingColumn]], bool] | None = None


# --- adapter ---


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


class Origin(Enum):
    """How an ORMAdapter was built."""

    SCRATCH = auto()  # new memory, created empty (from_scratch)
    EXISTING = auto()  # memory that already existed, with its records (from_existing)


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

    @property
    @abstractmethod
    def origin(self) -> Origin:
        """Which constructor created it."""

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


# --- files ---


@dataclass(frozen=True)
class FileInfo:
    """What the file system knows about a file. Timestamps in seconds since the epoch."""

    path: str  # relative to the adapter root, with "/"
    bytes: int
    modified: float  # mtime
    created: float | None  # None if the system doesn't provide it (Linux)
    changed: float  # ctime
    accessed: float  # atime
    permissions: str  # octal, "644"


class FileReader(ABC):
    """Reading files under a root (feature 013): what an ingestion source needs (feature 030: a source is read-only,
    an external SQL database will implement only this). Paths are relative to the root, as text with "/"; "" is the
    root. Every failure is raised as FileError."""

    @abstractmethod
    def absolute(self, path: str = "") -> str:
        """The full path, to show it or pass it to another tool (for example, the SQLite URL)."""

    @abstractmethod
    def exists(self, path: str = "") -> bool: ...

    @abstractmethod
    def is_file(self, path: str) -> bool: ...

    @abstractmethod
    def is_dir(self, path: str = "") -> bool: ...

    @abstractmethod
    def list_files(self) -> list[FileInfo]:
        """All the regular files under the root, at any level; skips the ones that can't be read."""

    @abstractmethod
    def info(self, path: str) -> FileInfo: ...

    @abstractmethod
    def hash(self, path: str) -> str:
        """sha256 of the content."""

    @abstractmethod
    def read_text(self, path: str, encoding: str = "utf-8") -> str: ...

    @abstractmethod
    def read_chunks(self, path: str, chunk_size: int = 1 << 20) -> Iterator[bytes]:
        """The content in blocks of up to `chunk_size` bytes, to stream it without loading it whole (feature 022).
        Opens the file right away (FileError if it doesn't exist, can't be read or falls outside the root) and closes
        it when the iteration ends or the iterator is closed."""


class FileWriter(ABC):
    """Changing files under a root (ingesta/, or base/ only when moving). Paths and errors as in FileReader."""

    @abstractmethod
    def write_text(self, path: str, text: str, encoding: str = "utf-8") -> None:
        """Writes the text as it is (without converting line endings), creating the missing folders."""

    @abstractmethod
    def write_bytes(self, path: str, data: bytes) -> None:
        """Writes the bytes, creating the missing folders."""

    @abstractmethod
    def make_dir(self, path: str = "") -> None:
        """Creates the folder and the missing ones above it; doesn't fail if it already exists."""

    @abstractmethod
    def free_name(self, folder: str, name: str) -> str:
        """folder/name, or folder/name__N.ext if it already exists, so nothing is overwritten."""

    @abstractmethod
    def copy_from(self, source: FileReader, path: str, target: str) -> str:
        """Copies `path` from `source` to `target` and returns the sha256 of what was written. Atomic: if interrupted,
        no half-written file is left with the final name. From an adapter of the same kind it also keeps the dates
        and permissions."""

    @abstractmethod
    def move(self, path: str, target: str) -> None:
        """Renames inside the same root (replaces `target` if it exists)."""

    @abstractmethod
    def delete(self, path: str, missing_ok: bool = False) -> None: ...

    @abstractmethod
    def remove_empty_dirs(self, folder: str) -> None:
        """Deletes `folder` and the ones above it while they are empty, never deleting the root."""


class FileAdapter(FileReader, FileWriter):
    """Files under a root that can be read and changed: one adapter per folder (base/, ingesta/...)."""


# --- repositories: the domain only knows these interfaces ---


class FileRepository(Protocol):
    def processed_origins(self) -> set[str]: ...

    def find(self, origin: str) -> FileRecord | None:
        """The record of that origin, or None if it isn't registered."""
        ...

    def with_hash(self, sha256: str) -> list[FileRecord]:
        """The records with that content (several if it was ingested more than once), by origin."""
        ...

    def all(self) -> list[FileRecord]: ...

    def insert(self, record: FileRecord) -> None:
        """Raises MemoryStoreError if it could not be stored."""
        ...

    def update_action(self, origin: str, action: str) -> None: ...

    def without_hash(self) -> list[FileRecord]: ...

    def save_hashes(self, hashes: Iterable[tuple[str, str]]) -> None:
        """Receives (origin, sha256) pairs."""
        ...

    def without_metadata(self) -> list[FileRecord]:
        """Records from before feature 009, without file system metadata."""
        ...

    def save_metadata(self, metadata: Iterable[tuple[str, FileMetadata]]) -> None:
        """Receives (origin, metadata) pairs."""
        ...

    def update_location(self, origin: str, file_type: str, target: str) -> None: ...

    def with_repeated_hash(self) -> list[FileRecord]:
        """All the records whose sha256 appears more than once."""
        ...


class CategoryRepository(Protocol):
    def sync_catalog(self, definitions: Iterable[CategoryDefinition]) -> None:
        """Makes the `categorias` catalog equal to the definitions (adds and updates)."""
        ...

    def all(self) -> list[FileCategory]: ...

    def add(self, rows: Iterable[FileCategory]) -> None: ...

    def remove(self, pairs: Iterable[tuple[str, str]]) -> None:
        """Receives (origin, category) pairs."""
        ...

    def mark_main(self, rows: Iterable[FileCategory]) -> None:
        """Updates the `principal` field of existing rows."""
        ...

    def origins_with(self, category: str) -> set[str]:
        """Origins of the files that have that category (main or not)."""
        ...


class RunRepository(Protocol):
    def start(self, start: str, action: str) -> int: ...

    def finish(self, run_id: int, end: str, new: int, skipped: int, errors: int) -> None: ...

    def last_finished(self) -> Run | None:
        """The last run that finished (the one with the latest `fin`), or None if none ever finished."""
        ...
