"""Opening of the Neo4j graph for the data module. Neither the driver (the `data` extra) nor a running Neo4j are
required: if anything fails, data is mounted on top of UnavailableGraph and answers 503 with the reason.

If Neo4j only fails to answer (Docker still starting, feature 054), the graph is a ReconnectingGraph: it tries again
when it is used, at most every RECONNECT_EVERY seconds, and becomes the real one as soon as Neo4j answers."""

import threading
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import LiteralString

from data.config import PASSWORD_VARIABLE
from data.models import GraphAdapter, GraphError, GraphRow, GraphTransaction, Parameters
from data.repository import PiaaRepository

from .settings import ServerSettings

RECONNECT_EVERY = 5.0  # seconds between two attempts to reach a Neo4j that didn't answer

type Connect = Callable[[], GraphAdapter]


class UnavailableGraph(GraphAdapter):
    """Stand-in for the graph when Neo4j can't be used: every operation raises GraphError (→ 503 in data)."""

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def verify(self) -> None:
        raise GraphError(self.reason)

    def read(self, cypher: LiteralString, parameters: Parameters | None = None) -> list[GraphRow]:
        raise GraphError(self.reason)

    def write(self, cypher: LiteralString, parameters: Parameters | None = None) -> list[GraphRow]:
        raise GraphError(self.reason)

    def transaction(self) -> AbstractContextManager[GraphTransaction]:
        raise GraphError(self.reason)

    def close(self) -> None:
        pass


class ReconnectingGraph(GraphAdapter):
    """A graph whose Neo4j didn't answer at start: every use tries `connect` again (at most every `every` seconds,
    so many requests at once don't flood Neo4j) and raises GraphError with the last reason until it answers; then it
    delegates to the connected adapter for good. Safe between threads: only one attempt runs at a time."""

    def __init__(
        self,
        connect: Connect,
        reason: str,
        every: float = RECONNECT_EVERY,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._connect = connect
        self._every = every
        self._clock = clock
        self._lock = threading.Lock()
        self._graph: GraphAdapter | None = None
        self._tried_at = clock()  # whoever builds it has just tried
        self._closed = False
        self.reason = reason

    @property
    def connected(self) -> bool:
        return self._graph is not None

    def _current(self) -> GraphAdapter:
        graph = self._graph
        if graph is not None:
            return graph
        with self._lock:
            if self._graph is not None:
                return self._graph
            if self._closed or self._clock() - self._tried_at < self._every:
                raise GraphError(self.reason)
            self._tried_at = self._clock()
            try:
                self._graph = self._connect()
            except GraphError as error:
                self.reason = str(error)
                raise
            return self._graph

    def verify(self) -> None:
        self._current().verify()

    def read(self, cypher: LiteralString, parameters: Parameters | None = None) -> list[GraphRow]:
        return self._current().read(cypher, parameters)

    def write(self, cypher: LiteralString, parameters: Parameters | None = None) -> list[GraphRow]:
        return self._current().write(cypher, parameters)

    def transaction(self) -> AbstractContextManager[GraphTransaction]:
        return self._current().transaction()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            if self._graph is not None:
                self._graph.close()


def open_graph(settings: ServerSettings) -> GraphAdapter:
    """The connected graph (with the piaa_id_<LABEL> constraints created); a ReconnectingGraph if Neo4j didn't answer
    (it keeps trying); or an UnavailableGraph that says why it never can (no password, no driver)."""
    password = settings.neo4j_password
    if password is None:
        return UnavailableGraph(f"Neo4j is not configured: the {PASSWORD_VARIABLE} environment variable is missing")
    try:
        from data.adapters import Neo4jGraphAdapter  # deferred: it imports the driver (the `data` extra)
    except ImportError:
        return UnavailableGraph("the Neo4j driver is not installed: uv sync --extra data")
    neo4j = settings.data

    def connect() -> GraphAdapter:
        graph = Neo4jGraphAdapter(password, neo4j.url, neo4j.user, neo4j.database)
        try:
            graph.verify()
            PiaaRepository(graph).ensure_constraints()
        except GraphError:
            graph.close()
            raise
        return graph

    try:
        return connect()
    except GraphError as error:
        return ReconnectingGraph(connect, str(error))
