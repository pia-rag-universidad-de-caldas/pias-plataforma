"""A graph whose Neo4j didn't answer at start (feature 054): it tries again when used, at most every few seconds, and
becomes the real one once Neo4j answers."""

import threading
from contextlib import AbstractContextManager
from typing import LiteralString

import pytest

from data.models import GraphAdapter, GraphError, GraphRow, GraphTransaction, Parameters
from server.graph import ReconnectingGraph


class Answering(GraphAdapter):
    def __init__(self) -> None:
        self.closed = False

    def verify(self) -> None:
        pass

    def read(self, cypher: LiteralString, parameters: Parameters | None = None) -> list[GraphRow]:
        return [{"read": cypher}]

    def write(self, cypher: LiteralString, parameters: Parameters | None = None) -> list[GraphRow]:
        return [{"written": cypher}]

    def transaction(self) -> AbstractContextManager[GraphTransaction]:
        raise NotImplementedError

    def close(self) -> None:
        self.closed = True


class Neo4j:
    """Down for the first `failures` attempts, then answers."""

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.attempts = 0
        self.graph = Answering()

    def __call__(self) -> GraphAdapter:
        self.attempts += 1
        if self.attempts <= self.failures:
            raise GraphError(f"down ({self.attempts})")
        return self.graph


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_it_answers_with_the_reason_until_neo4j_answers() -> None:
    neo4j, clock = Neo4j(failures=1), Clock()
    graph = ReconnectingGraph(neo4j, "down at start", every=5, clock=clock)
    with pytest.raises(GraphError, match="down at start"):
        graph.verify()  # just tried by whoever built it: not again yet
    clock.now = 5
    with pytest.raises(GraphError, match=r"down \(1\)"):
        graph.verify()
    assert not graph.connected
    clock.now = 10
    assert graph.read("RETURN 1") == [{"read": "RETURN 1"}]
    assert graph.connected


def test_once_connected_it_never_tries_again() -> None:
    neo4j, clock = Neo4j(failures=0), Clock()
    graph = ReconnectingGraph(neo4j, "down", every=5, clock=clock)
    clock.now = 5
    graph.verify()
    graph.write("CREATE ()")
    graph.read("RETURN 1")
    assert neo4j.attempts == 1


def test_many_uses_in_a_row_make_a_single_attempt() -> None:
    neo4j, clock = Neo4j(failures=100), Clock()
    graph = ReconnectingGraph(neo4j, "down", every=5, clock=clock)
    clock.now = 5
    for _ in range(50):
        with pytest.raises(GraphError):
            graph.verify()
    assert neo4j.attempts == 1


def test_threads_at_once_make_a_single_attempt() -> None:
    neo4j, clock = Neo4j(failures=0), Clock()
    graph = ReconnectingGraph(neo4j, "down", every=5, clock=clock)
    clock.now = 5
    threads = [threading.Thread(target=graph.verify) for _ in range(20)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert neo4j.attempts == 1 and graph.connected


def test_closing_closes_the_real_graph_and_stops_trying() -> None:
    neo4j, clock = Neo4j(failures=0), Clock()
    graph = ReconnectingGraph(neo4j, "down", every=5, clock=clock)
    graph.close()
    clock.now = 5
    with pytest.raises(GraphError):
        graph.verify()
    assert neo4j.attempts == 0
    connected = ReconnectingGraph(neo4j, "down", every=5, clock=clock)
    clock.now = 10
    connected.verify()
    connected.close()
    assert neo4j.graph.closed
