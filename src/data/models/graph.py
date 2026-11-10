"""Graph contract (feature 015).

GraphAdapter: read and write with Cypher without knowing the driver. The implementation lives in adapters/, the only
package that imports neo4j. Cypher is a LiteralString: values always go in parameters, never concatenated.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from types import TracebackType
from typing import LiteralString, Self

type GraphValue = str | int | float | bool | Sequence[GraphValue] | Mapping[str, GraphValue] | None
type GraphRow = dict[str, GraphValue]  # one result row: RETURN column → value
type Parameters = Mapping[str, GraphValue]


class GraphError(Exception):
    """The graph did not answer or rejected a query. Raised by the adapter so nobody depends on the driver."""


class GraphTransaction(ABC):
    """An open write transaction (feature 022): every statement run in it is committed together or not at all."""

    @abstractmethod
    def run(self, cypher: LiteralString, parameters: Parameters | None = None) -> list[GraphRow]:
        """Runs a statement inside the transaction and returns its rows."""


class GraphAdapter(ABC):
    """Connection to the graph. Use it with `with` or close it with close()."""

    @abstractmethod
    def verify(self) -> None:
        """Checks that the server answers and accepts the credentials; otherwise GraphError."""

    @abstractmethod
    def read(self, cypher: LiteralString, parameters: Parameters | None = None) -> list[GraphRow]:
        """Runs a read-only query and returns its rows."""

    @abstractmethod
    def write(self, cypher: LiteralString, parameters: Parameters | None = None) -> list[GraphRow]:
        """Runs a query that changes the graph, in its own transaction, and returns its rows."""

    @abstractmethod
    def transaction(self) -> AbstractContextManager[GraphTransaction]:
        """`with graph.transaction() as tx:` commits when the block ends; any exception raised inside it (also one
        from the caller, to abort) rolls everything back and propagates. Driver failures come out as GraphError."""

    @abstractmethod
    def close(self) -> None:
        """Releases the connection."""

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, kind: type[BaseException] | None, error: BaseException | None, traceback: TracebackType | None
    ) -> None:
        self.close()
