"""What a table of the memory is, without SQL or ORM syntax (feature 008): the project's ones are described in tables/
and the adapter (adapters/) translates them to its engine."""

from collections.abc import Callable
from dataclasses import Field, dataclass
from enum import Enum, auto
from typing import ClassVar, Protocol

Value = str | int | bool | None  # simple value stored in a column


class Entity(Protocol):
    """A row of a table: any dataclass of models/entities.py."""

    __dataclass_fields__: ClassVar[dict[str, Field[object]]]


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
    created_if_missing: bool = False  # added after memories already existed: opening one creates it (feature 041)
