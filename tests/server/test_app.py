"""The root app (feature 040): which hosts it answers to, its body limit and its socket, whatever the module."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from data.api import ApiSettings as DataSettings
from ingesta.api import ApiSettings
from server.app import create_app
from server.graph import UnavailableGraph
from server.settings import MAX_BODY_BYTES, ServerSettings

LOCAL = {"Host": "localhost:8000"}  # the socket of TestClient doesn't take its base_url


def server(
    folder: Path,
    url: str = "http://127.0.0.1:8000",
    allowed_hosts: tuple[str, ...] = (),
    max_body_bytes: int = MAX_BODY_BYTES,
) -> TestClient:
    settings = ServerSettings(
        ApiSettings(str(folder / "base"), str(folder / "ingesta"), f"sqlite:///{folder / 'memory.sqlite3'}"),
        DataSettings("neo4j://localhost:1", "neo4j", None),
        url,
        allowed_hosts=allowed_hosts,
        max_body_bytes=max_body_bytes,
    )
    return TestClient(create_app(settings, UnavailableGraph("no Neo4j")), base_url="http://localhost:8000")


@pytest.mark.parametrize("host", ["localhost:8000", "127.0.0.1:8000", "[::1]:8000"])
def test_the_local_names_are_answered(tmp_path: Path, host: str) -> None:
    assert server(tmp_path).get("/health", headers={"Host": host}).status_code == 200


def test_the_host_of_self_url_is_answered(tmp_path: Path) -> None:
    client = server(tmp_path, "http://10.1.2.3:8000")
    assert client.get("/health", headers={"Host": "10.1.2.3:8000"}).status_code == 200


def test_an_allowed_host_is_answered(tmp_path: Path) -> None:
    client = server(tmp_path, allowed_hosts=("pias.local",))
    assert client.get("/health", headers={"Host": "pias.local"}).status_code == 200


@pytest.mark.parametrize(
    "path", ["/health", "/ingesta/health", "/data/health", "/chunking/docs", "/llm/health", "/pipeline/health"]
)
def test_another_host_is_400_in_every_module(tmp_path: Path, path: str) -> None:
    assert server(tmp_path).get(path, headers={"Host": "evil.example"}).status_code == 400


def test_a_body_over_the_limit_is_413_in_a_module(tmp_path: Path) -> None:
    client = server(tmp_path, max_body_bytes=100)
    assert client.post("/data/batch", content=b"x" * 101).status_code == 413


@pytest.mark.parametrize("path", ["/processes/ws", "/ingesta/processes/ws"])
def test_a_socket_from_another_site_is_refused(tmp_path: Path, path: str) -> None:
    headers = {**LOCAL, "Origin": "http://evil.example"}
    with pytest.raises(WebSocketDisconnect), server(tmp_path).websocket_connect(path, headers=headers):
        pass


def test_a_socket_on_another_host_is_refused(tmp_path: Path) -> None:
    headers = {"Host": "evil.example"}
    with pytest.raises(WebSocketDisconnect), server(tmp_path).websocket_connect("/processes/ws", headers=headers):
        pass


def test_the_socket_accepts_a_client_without_origin(tmp_path: Path) -> None:
    with server(tmp_path).websocket_connect("/ingesta/processes/ws", headers=LOCAL) as socket:
        assert "counts" in socket.receive_json()
