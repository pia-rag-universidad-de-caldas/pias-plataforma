"""SQLConverter with SQLAlchemy: translates the project's tables and filters and runs them against the database.

The only file that imports SQLAlchemy (Ruff enforces it with TID251 outside adapters/). The engine is chosen with
the URL (sqlite:///path, postgresql+psycopg://...).
"""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import fields, is_dataclass
from typing import Any, ClassVar

from sqlalchemy import (
    Boolean,
    Column,
    ColumnElement,
    Connection,
    Engine,
    ForeignKey,
    Integer,
    MetaData,
    Table,
    Text,
    create_engine,
    delete,
    false,
    func,
    insert,
    inspect,
    literal,
    make_url,
    select,
    true,
    update,
)
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.sql.elements import TextClause
from sqlalchemy.sql.expression import text
from sqlalchemy.types import TypeEngine

from ingesta.models import (
    ColumnSpec,
    DataType,
    ExistingColumn,
    Filter,
    MemoryStoreError,
    Operator,
    Row,
    SQLConverter,
    TableSpec,
    Value,
)

from .local_files import folder_and_name

Fields = tuple[str, ...]


class SqlAlchemyConverter(SQLConverter):
    _TYPES: ClassVar[dict[DataType, type[TypeEngine[Any]]]] = {
        DataType.TEXT: Text,
        DataType.INTEGER: Integer,
        DataType.BOOLEAN: Boolean,
    }

    def __init__(self) -> None:
        self._engine: Engine | None = None
        self._metadata = MetaData()
        self._tables: dict[type[object], tuple[Table, Fields]] = {}
        self._active_connection: Connection | None = None  # the one of the transaction opened with `transaction()`

    # --- connection ---

    def exists(self, url: str) -> bool:
        file = self._sqlite_file(url)
        if file is not None:
            folder, name = folder_and_name(file)
            if not folder.is_file(name):
                return False  # connecting would create an empty file
        engine = create_engine(url)
        try:
            with engine.connect() as con:
                return bool(inspect(con).get_table_names())
        except SQLAlchemyError as e:
            raise MemoryStoreError(f"could not open the memory: {self._reason(e)}") from e
        finally:
            engine.dispose()

    def open(self, url: str) -> None:
        file = self._sqlite_file(url)
        arguments: dict[str, Any] = {}
        if file is not None:
            folder_and_name(file)[0].make_dir()  # SQLite creates the file but not its folder
        if make_url(url).get_backend_name() == "sqlite":
            # PEP 249 transaction mode (Python 3.12): DDL also goes inside the transaction, so a migration that
            # fails halfway is rolled back entirely.
            arguments["connect_args"] = {"autocommit": False}
        self._engine = create_engine(url, **arguments)

    def close(self) -> None:
        if self._engine is not None:
            self._engine.dispose()

    def visible_url(self, url: str) -> str:
        return make_url(url).render_as_string(hide_password=True)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        if self._active_connection is not None:  # nested: joins the open one
            yield
            return
        try:
            with self._opened_engine().begin() as con:
                self._active_connection = con
                try:
                    yield
                finally:
                    self._active_connection = None
        except SQLAlchemyError as e:
            raise MemoryStoreError(f"could not commit the transaction: {self._reason(e)}") from e

    def _opened_engine(self) -> Engine:
        if self._engine is None:
            raise RuntimeError("the converter is not connected: open(url) is missing")
        return self._engine

    @contextmanager
    def _connection(self, action: str) -> Iterator[Connection]:
        """The connection of the open transaction or, if there is none, an own transaction committed on exit."""
        try:
            if self._active_connection is not None:
                yield self._active_connection
            else:
                with self._opened_engine().begin() as con:
                    yield con
        except SQLAlchemyError as e:
            raise MemoryStoreError(f"could not {action}: {self._reason(e)}") from e

    # --- schema ---

    def register(self, tables: Sequence[TableSpec]) -> None:
        for table in tables:
            self._tables[table.entity] = (self._table(table), self._fields_of(table))

    def create_tables(self, tables: Sequence[TableSpec]) -> None:
        translated = [self._entity(t.entity)[0] for t in tables]
        with self._connection("create the tables") as con:
            self._metadata.create_all(con, tables=translated)

    def columns(self, table: str) -> list[ExistingColumn] | None:
        with self._connection("read the schema") as con:
            schema = inspect(con)
            if not schema.has_table(table):
                return None
            return [ExistingColumn(c["name"], c["nullable"]) for c in schema.get_columns(table)]

    def rebuild(self, table: TableSpec) -> None:
        new, _ = self._entity(table.entity)
        with self._connection(f"migrate the table {table.name}") as con:
            old = Table(table.name, MetaData(), autoload_with=con)
            rows = [{k: v for k, v in r.items() if k in new.c} for r in con.execute(select(old)).mappings()]
            old.drop(con)
            new.create(con)
            if rows:
                con.execute(insert(new), rows)

    # --- registered entities ---

    def fields(self, entity: type[object]) -> tuple[str, ...]:
        return self._entity(entity)[1]

    def primary_key(self, entity: type[object]) -> tuple[str, ...]:
        return tuple(c.name for c in self._entity(entity)[0].primary_key.columns)

    def _entity(self, entity: type[object]) -> tuple[Table, Fields]:
        try:
            return self._tables[entity]
        except KeyError:
            raise ValueError(f"{entity.__name__} is not in the registered tables") from None

    # --- data ---

    def insert(self, entity: type[object], row: Row) -> Value:
        table, _ = self._entity(entity)
        with self._connection("write to the memory") as con:
            inserted_key = con.execute(insert(table).values(self._values(table, row))).inserted_primary_key
            generated: Value = inserted_key[0] if inserted_key else None
            return generated

    def select(self, entity: type[object], filters: Sequence[Filter], order: Sequence[str]) -> list[Row]:
        table, entity_fields = self._entity(entity)
        query = (
            select(*(self._column(table, c) for c in entity_fields))
            .where(*self._conditions(table, filters))
            .order_by(*(self._column(table, c) for c in order))
        )
        with self._connection("read the memory") as con:
            return [dict(zip(entity_fields, r, strict=True)) for r in con.execute(query)]

    def update(self, entity: type[object], filters: Sequence[Filter], row: Row) -> None:
        table, _ = self._entity(entity)
        query = update(table).where(*self._conditions(table, filters)).values(self._values(table, row))
        with self._connection("update the memory") as con:
            con.execute(query)

    def delete(self, entity: type[object], filters: Sequence[Filter]) -> None:
        table, _ = self._entity(entity)
        with self._connection("delete from the memory") as con:
            con.execute(delete(table).where(*self._conditions(table, filters)))

    # --- translation ---

    def _table(self, table: TableSpec) -> Table:
        """The translation of `table` (only once per name)."""
        if table.name in self._metadata.tables:
            return self._metadata.tables[table.name]
        return Table(
            table.name,
            self._metadata,
            *(self._sa_column(c) for c in table.columns),
            sqlite_autoincrement=any(c.autoincrement for c in table.columns),
        )

    def _sa_column(self, c: ColumnSpec) -> Column[Any]:
        foreign = (ForeignKey(c.reference),) if c.reference else ()
        return Column(
            c.name,
            self._TYPES[c.type],
            *foreign,
            primary_key=c.key,
            nullable=c.nullable,
            index=c.index or None,
            server_default=self._default(c.default),
        )

    @staticmethod
    def _default(value: Value) -> ColumnElement[Any] | TextClause | None:
        """Default value in the database, written as each engine understands it."""
        match value:
            case None:
                return None
            case bool():
                return true() if value else false()
            case int():
                return text(str(value))
            case str():
                return literal(value)

    @staticmethod
    def _fields_of(table: TableSpec) -> Fields:
        """Fields of the entity; they must match the table's columns."""
        if not is_dataclass(table.entity):
            raise ValueError(f"the entity of {table.name} is not a dataclass")
        entity_fields = tuple(f.name for f in fields(table.entity))
        if set(entity_fields) != {c.name for c in table.columns}:
            raise ValueError(f"{table.entity.__name__} and the table {table.name} don't have the same fields")
        return entity_fields

    @staticmethod
    def _column(table: Table, field: str) -> Column[Any]:
        if field not in table.c:
            raise ValueError(f"{table.name} has no field {field!r}")
        return table.c[field]

    def _conditions(self, table: Table, filters: Sequence[Filter]) -> list[ColumnElement[bool]]:
        return [self._condition(table, f) for f in filters]

    def _condition(self, table: Table, filter_: Filter) -> ColumnElement[bool]:
        column = self._column(table, filter_.field)
        match filter_.operator:
            case Operator.EQUAL:
                return column == filter_.value
            case Operator.NOT_EQUAL:
                return column != filter_.value
            case Operator.IS_NULL:
                return column.is_(None)
            case Operator.NOT_NULL:
                return column.is_not(None)
            case Operator.REPEATED:
                repeated = select(column).where(column.is_not(None)).group_by(column).having(func.count() > 1)
                return column.in_(repeated)

    def _values(self, table: Table, row: Row) -> Row:
        return {self._column(table, field).name: value for field, value in row.items()}

    @staticmethod
    def _reason(e: SQLAlchemyError) -> str:
        """Only the engine's message, without the SQL or the parameters SQLAlchemy adds."""
        return str(e.orig) if isinstance(e, DBAPIError) else str(e).splitlines()[0]

    @staticmethod
    def _sqlite_file(url: str) -> str | None:
        """The file of an on-disk SQLite database; None if it is another engine or in-memory SQLite."""
        data = make_url(url)
        if data.get_backend_name() == "sqlite" and data.database and data.database != ":memory:":
            return data.database
        return None
