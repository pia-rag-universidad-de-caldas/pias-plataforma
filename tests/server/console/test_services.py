"""Neo4j with Docker (feature 034): what the console runs depending on what answers, with a fake docker and port."""

import subprocess
from collections.abc import Sequence

from server.console.services import NEO4J_TIMEOUT, Neo4jService, neo4j_browser
from server.console.settings import ConsoleSettings


def settings(
    url: str = "neo4j://localhost:7688", password: str | None = "secreta123", docker: bool = True
) -> ConsoleSettings:
    return ConsoleSettings("http://127.0.0.1:8000", url, "neo4j", "neo4j", password, docker=docker)


class Docker:
    """Records each docker command; `container` is None (not created), "true" (running) or "false" (stopped)."""

    def __init__(self, container: str | None, installed: bool = True) -> None:
        self.container = container
        self.installed = installed
        self.commands: list[list[str]] = []

    def __call__(self, command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        if not self.installed:
            raise FileNotFoundError("docker")
        self.commands.append(list(command))
        if command[1] == "container":
            found = self.container is not None
            return subprocess.CompletedProcess(command, 0 if found else 1, f"{self.container}\n", "")
        return subprocess.CompletedProcess(command, 0, "", "")


class Port:
    """Closed until a docker command opens it (or for good with `opens=False`)."""

    def __init__(self, docker: Docker, open_at_first: bool = False, opens: bool = True) -> None:
        self.docker = docker
        self.open_at_first = open_at_first
        self.opens = opens
        self.asked: list[tuple[str, int]] = []

    def __call__(self, host: str, port: int) -> bool:
        self.asked.append((host, port))
        started = any(c[1] in ("start", "run") for c in self.docker.commands)
        return self.open_at_first or (self.opens and started)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def service(config: ConsoleSettings, docker: Docker, port: Port, clock: Clock | None = None) -> Neo4jService:
    clock = clock or Clock()
    return Neo4jService(config, run=docker, probe=port, sleep=clock.sleep, clock=clock)


def test_a_neo4j_that_answers_is_used_as_it_is() -> None:
    docker = Docker(None)
    state = service(settings(), docker, Port(docker, open_at_first=True)).ensure(print)
    assert state.ready and docker.commands == []


def test_a_stopped_container_is_started() -> None:
    docker = Docker("false")
    port = Port(docker)
    state = service(settings(), docker, port).ensure(print)
    assert state.ready
    assert docker.commands[-1] == ["docker", "start", "prueba-chunking-neo4j"]
    assert port.asked[0] == ("localhost", 7688)


def test_a_missing_container_is_created_with_the_password_and_port() -> None:
    docker = Docker(None)
    state = service(settings(), docker, Port(docker)).ensure(print)
    run = docker.commands[-1]
    assert state.ready and run[:2] == ["docker", "run"]
    assert "7688:7687" in run and "NEO4J_AUTH=neo4j/secreta123" in run and run[-1] == "neo4j:2026.07.1"


def test_without_a_valid_password_nothing_is_created() -> None:
    docker = Docker(None)
    state = service(settings(password="corta"), docker, Port(docker)).ensure(print)
    assert not state.ready and "8 caracteres o más" in state.detail
    assert all(c[1] != "run" for c in docker.commands)


def test_remote_disabled_or_missing_docker_is_never_run() -> None:
    for config, docker in [
        (settings(url="neo4j://graph.example:7687"), Docker(None)),
        (settings(docker=False), Docker(None)),
        (settings(), Docker(None, installed=False)),
    ]:
        state = service(config, docker, Port(docker)).ensure(print)
        assert not state.ready and docker.commands == []


def test_a_container_that_never_answers_times_out() -> None:
    docker = Docker("true")
    clock = Clock()
    state = service(settings(), docker, Port(docker, opens=False), clock).ensure(print)
    assert not state.ready and "no respondió" in state.detail
    assert clock.now >= NEO4J_TIMEOUT
    assert all(c[1] != "start" for c in docker.commands)  # already running: only waited for


def test_the_neo4j_browser_uses_the_http_port_published_next_to_the_bolt() -> None:
    def ps(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        ports = "0.0.0.0:17474->7474/tcp, 0.0.0.0:17687->7687/tcp\n0.0.0.0:7474->7474/tcp, 0.0.0.0:7687->7687/tcp\n"
        return subprocess.CompletedProcess(command, 0, ports, "")

    url = neo4j_browser(settings(url="neo4j://localhost:17687"), run=ps)
    assert url.startswith("http://localhost:17474/browser/?dbms=neo4j%3A%2F%2Fneo4j%40localhost%3A17687")
    assert neo4j_browser(settings(url="neo4j://localhost:9999"), run=ps).startswith("http://localhost:7474/")
