"""The real server app for the console's tests: the graph unavailable and a memory that doesn't exist (the OpenAPI
doesn't need either), reached through ApiClient as the console reaches it."""

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from data.api import ApiSettings as DataSettings
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
