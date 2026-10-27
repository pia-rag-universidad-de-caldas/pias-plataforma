"""Opening of the Neo4j graph for the data module. Neither the driver (the `data` extra) nor a running Neo4j are
required: if anything fails, data is mounted on top of UnavailableGraph and answers 503 with the reason."""

from contextlib import AbstractContextManager
from typing import LiteralString

from data.config import PASSWORD_VARIABLE
from data.models import GraphAdapter, GraphError, GraphRow, GraphTransaction, Parameters
from data.repository import PiaaRepository

from .settings import ServerSettings


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


def open_graph(settings: ServerSettings) -> GraphAdapter:
    """The connected graph (with the piaa_id_<LABEL> constraints created, like `prueba-chunking-data serve`), or an
    UnavailableGraph that says why not."""
    if settings.neo4j_password is None:
        return UnavailableGraph(f"Neo4j is not configured: the {PASSWORD_VARIABLE} environment variable is missing")
    try:
        from data.adapters import Neo4jGraphAdapter  # deferred: it imports the driver (the `data` extra)
    except ImportError:
        return UnavailableGraph("the Neo4j driver is not installed: uv sync --extra data")
    neo4j = settings.data
    try:
        graph = Neo4jGraphAdapter(settings.neo4j_password, neo4j.url, neo4j.user, neo4j.database)
    except GraphError as error:
        return UnavailableGraph(str(error))
    try:
        graph.verify()
        PiaaRepository(graph).ensure_constraints()
    except GraphError as error:
        graph.close()
        return UnavailableGraph(str(error))
    return graph
