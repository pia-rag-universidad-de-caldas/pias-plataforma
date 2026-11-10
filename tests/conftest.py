"""Fixtures shared by tests of different folders. Only one conftest.py can exist: without __init__.py, mypy rejects two
modules with the same name.

- `client`, `operations`, `find`: the real server app for the console's tests, with the graph unavailable and a memory
  that doesn't exist (the OpenAPI doesn't need either), reached through ApiClient as the console reaches it.
- `write_file`: a file under a folder of a test.
- `data_client`: the app of `data` over a graph that gives the rows a test scripts.
- `real_graph`, `test_prefix`: a real Neo4j, only if NEO4J_TEST_URL says which (`neo4j` tests). A test only uses ids
  that start with its prefix, and only those are deleted when it ends.
- `fake_data`: data's node and batch routes over a dict, as an httpx.MockTransport (feature 042: what ingesta and
  parsing write and read there).
"""

import os
import uuid
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import LiteralString

import pytest
from fakes import FakeData
from fastapi.testclient import TestClient

from data.api import ApiSettings as DataSettings
from data.api import create_app as create_data_app
from data.models import GraphAdapter, GraphRow, GraphTransaction, Parameters
from ingesta.api import ApiSettings
from server.app import create_app
from server.console.catalog import MODULES, Operation
from server.console.client import ApiClient
from server.graph import UnavailableGraph
from server.settings import ServerSettings


@pytest.fixture(scope="session")
def client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[ApiClient]:
    folder: Path = tmp_path_factory.mktemp("console")
    settings = ServerSettings(
        ApiSettings(str(folder / "base"), str(folder / "ingesta"), f"sqlite:///{folder / 'memory.sqlite3'}"),
        DataSettings("neo4j://localhost:1", "neo4j", None),
        "http://127.0.0.1:8000",
        allowed_hosts=("testserver",),
    )
    with TestClient(create_app(settings, UnavailableGraph("no Neo4j in tests"))) as test_client:
        yield ApiClient(test_client)


@pytest.fixture(scope="session")
def operations(client: ApiClient) -> dict[str, tuple[Operation, ...]]:
    return {module.name: client.operations(module) for module in MODULES}


type Find = Callable[[str, str, str], Operation]


@pytest.fixture(scope="session")
def find(operations: dict[str, tuple[Operation, ...]]) -> Find:
    """The operation of a module by method and path."""

    def found(name: str, method: str, path: str) -> Operation:
        return next(op for op in operations[name] if (op.method, op.path) == (method, path))

    return found


CHUNKABLE_PDF = b"%PDF-1.4\n" + b"x" * 2048  # over ALMOST_EMPTY_THRESHOLD


type WriteFile = Callable[..., None]


@pytest.fixture(scope="session")
def write_file() -> WriteFile:
    """`write_file(root, relative)` writes a chunkable pdf; a third argument, those bytes."""

    def write(root: Path, relative: str, content: bytes = CHUNKABLE_PDF) -> None:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    return write


class _ScriptedTransaction(GraphTransaction):
    def run(self, cypher: LiteralString, parameters: Parameters | None = None) -> list[GraphRow]:
        raise AssertionError("these routes don't open transactions")


class _ScriptedGraph(GraphAdapter):
    """Answers each query with the next rows of the script; a query past its end fails the test."""

    def __init__(self, answers: Sequence[list[GraphRow]]) -> None:
        self._answers = iter(answers)

    def verify(self) -> None:
        pass

    def read(self, cypher: LiteralString, parameters: Parameters | None = None) -> list[GraphRow]:
        return next(self._answers)

    def write(self, cypher: LiteralString, parameters: Parameters | None = None) -> list[GraphRow]:
        return next(self._answers)

    @contextmanager
    def transaction(self) -> Iterator[GraphTransaction]:
        yield _ScriptedTransaction()

    def close(self) -> None:
        pass


type DataClient = Callable[..., TestClient]


@pytest.fixture
def data_client() -> DataClient:
    """`data_client(rows_of_query_1, rows_of_query_2...)`."""

    def build(*answers: list[GraphRow]) -> TestClient:
        settings = DataSettings("neo4j://localhost:1", "neo4j", None)
        return TestClient(create_data_app(settings, _ScriptedGraph(answers)))

    return build


@pytest.fixture(scope="session")
def real_graph() -> Iterator[GraphAdapter]:
    url = os.environ.get("NEO4J_TEST_URL")
    if not url:
        pytest.skip("NEO4J_TEST_URL doesn't say which Neo4j to use")
    pytest.importorskip("neo4j")
    from data.adapters import Neo4jGraphAdapter  # it needs the driver (the data extra)
    from data.repository import PiaaRepository

    password = os.environ.get("NEO4J_TEST_PASSWORD", "")
    with Neo4jGraphAdapter(password, url, os.environ.get("NEO4J_TEST_USER", "neo4j")) as graph:
        PiaaRepository(graph).ensure_constraints()
        yield graph


@pytest.fixture
def test_prefix(real_graph: GraphAdapter) -> Iterator[str]:
    prefix = f"test-neo4j-{uuid.uuid4().hex}"
    yield prefix
    real_graph.write("MATCH (n) WHERE n.id STARTS WITH $prefix DETACH DELETE n", {"prefix": prefix})


@pytest.fixture
def fake_data() -> FakeData:
    return FakeData()
