"""GraphAdapter on top of the official Neo4j driver. The ONLY file that imports neo4j (Ruff TID251)."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, LiteralString

from neo4j import Driver, GraphDatabase, RoutingControl, Transaction
from neo4j.exceptions import DriverError, Neo4jError

from data.config import NEO4J_DATABASE, NEO4J_URL, NEO4J_USER
from data.models import GraphAdapter, GraphError, GraphRow, GraphTransaction, Parameters


class _Neo4jTransaction(GraphTransaction):
    def __init__(self, transaction: Transaction) -> None:
        self._transaction = transaction

    def run(self, cypher: LiteralString, parameters: Parameters | None = None) -> list[GraphRow]:
        arguments: dict[str, Any] = dict(parameters or {})
        try:
            return self._transaction.run(cypher, arguments).data()
        except (DriverError, Neo4jError) as error:
            raise GraphError(f"query rejected: {error}") from error


class Neo4jGraphAdapter(GraphAdapter):
    def __init__(
        self,
        password: str,
        url: str = NEO4J_URL,
        user: str = NEO4J_USER,
        database: str | None = NEO4J_DATABASE,
    ) -> None:
        self._database = database
        try:
            self._driver: Driver = GraphDatabase.driver(url, auth=(user, password))
        except (DriverError, Neo4jError, ValueError) as error:
            raise GraphError(f"could not create the connection to {url}: {error}") from error

    def verify(self) -> None:
        try:
            self._driver.verify_connectivity()
        except (DriverError, Neo4jError) as error:
            raise GraphError(f"Neo4j is not answering: {error}") from error

    def read(self, cypher: LiteralString, parameters: Parameters | None = None) -> list[GraphRow]:
        return self._run(cypher, parameters, RoutingControl.READ)

    def write(self, cypher: LiteralString, parameters: Parameters | None = None) -> list[GraphRow]:
        return self._run(cypher, parameters, RoutingControl.WRITE)

    @contextmanager
    def transaction(self) -> Iterator[GraphTransaction]:
        """Explicit transaction (not execute_write: its retries would run the caller's block again)."""
        try:
            with self._driver.session(database=self._database) as session, session.begin_transaction() as tx:
                yield _Neo4jTransaction(tx)
                tx.commit()  # leaving the `with` without commit (an exception) rolls back
        except (DriverError, Neo4jError) as error:
            raise GraphError(f"transaction failed: {error}") from error

    def close(self) -> None:
        self._driver.close()

    def _run(self, cypher: LiteralString, parameters: Parameters | None, routing: RoutingControl) -> list[GraphRow]:
        arguments: dict[str, Any] = dict(parameters or {})
        try:
            result = self._driver.execute_query(cypher, arguments, routing_=routing, database_=self._database)
        except (DriverError, Neo4jError) as error:
            raise GraphError(f"query rejected: {error}") from error
        return [record.data() for record in result.records]
