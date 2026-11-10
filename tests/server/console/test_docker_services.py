"""Neo4j and Ollama with Docker Compose (features 034 and 054): what the console runs depending on what answers, with a
fake docker, fake ports and a fake clock."""

import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from server.console import docker_services as services
from server.console import docker_watchdog
from server.console.docker_services import DAEMON_TIMEOUT, NEO4J_TIMEOUT, DockerServices, neo4j_browser
from server.console.settings import ConsoleSettings

BOLT = ("localhost", 7688)
OLLAMA = ("127.0.0.1", 11434)


def settings(
    url: str = "neo4j://localhost:7688",
    password: str | None = "secreta123",
    docker: bool = True,
    keep: bool = False,
    gpu: str = "amd",
    ollama: str = "http://127.0.0.1:11434",
) -> ConsoleSettings:
    return ConsoleSettings(
        "http://127.0.0.1:8000",
        url,
        "neo4j",
        "neo4j",
        password,
        docker=docker,
        keep_docker=keep,
        gpu=gpu,
        ollama_url=ollama,
    )


def done(command: Sequence[str], code: int = 0, out: str = "", err: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, code, out, err)


class Docker:
    """Records each docker command. The daemon fails `daemon_down` times (None: always); `old` is the compose label
    of a container called prueba-chunking-neo4j ("" a standalone one, None no container); `running` what compose ps
    lists before anything is started."""

    def __init__(
        self,
        daemon_down: int | None = 0,
        old: str | None = None,
        old_running: bool = False,
        volume: bool = False,
        running: Sequence[str] = (),
        installed: bool = True,
        up_fails: bool = False,
    ) -> None:
        self.daemon_down = daemon_down
        self.old = old
        self.old_running = old_running
        self.volume = volume
        self.running = list(running)
        self.installed = installed
        self.up_fails = up_fails
        self.commands: list[list[str]] = []
        self.envs: list[Mapping[str, str] | None] = []
        self.up: set[str] = set()

    def __call__(
        self, command: Sequence[str], env: Mapping[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        if not self.installed:
            raise FileNotFoundError("docker")
        self.commands.append(list(command))
        self.envs.append(env)
        verb = command[1]
        if verb == "info":
            if self.daemon_down is None or self.daemon_down > 0:
                if self.daemon_down is not None:
                    self.daemon_down -= 1
                return done(command, 1, err="Cannot connect to the Docker daemon")
            return done(command, out="29.0\n")
        if verb == "container":
            if self.old is None:
                return done(command, 1)
            return done(command, 0, f"{str(self.old_running).lower()} {self.old}\n")
        if verb == "volume":
            return done(command, 0 if self.volume else 1)
        if verb == "compose":
            if "ps" in command:
                return done(command, out="\n".join(self.running))
            if "up" in command:
                if self.up_fails:
                    return done(command, 1, err="Error: port is already allocated")
                self.up |= {part for part in command if part in ("neo4j", "ollama")}
        return done(command)

    def composed(self, verb: str) -> list[list[str]]:
        return [c for c in self.commands if c[1] == "compose" and verb in c]


class Ports:
    """Which addresses answer: those open from the start and those of services compose started."""

    def __init__(self, docker: Docker, open_at_first: Sequence[tuple[str, int]] = (), opens: bool = True) -> None:
        self.docker = docker
        self.open_at_first = set(open_at_first)
        self.opens = opens

    def __call__(self, host: str, port: int) -> bool:
        started = (host, port) == BOLT and "neo4j" in self.docker.up
        return (host, port) in self.open_at_first or (self.opens and started)


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class Watched:
    """Stands in for the watchdog: what it would run, and whether the console released it."""

    def __init__(self) -> None:
        self.commands: list[list[str]] = []
        self.released = False

    def __call__(self, command: Sequence[str], env: Mapping[str, str]) -> "Watched":
        self.commands.append(list(command))
        return self

    def release(self) -> None:
        self.released = True


def service(
    config: ConsoleSettings,
    docker: Docker,
    ports: Ports | None = None,
    clock: Clock | None = None,
    watch: Watched | None = None,
) -> DockerServices:
    clock = clock or Clock()
    return DockerServices(
        config,
        "/repo/docker",
        run=docker,
        probe=ports or Ports(docker),
        sleep=clock.sleep,
        clock=clock,
        watch=watch or Watched(),
        groups=lambda name: {"video": 985, "render": 989}.get(name),
    )


def test_services_that_answer_are_used_as_they_are() -> None:
    docker = Docker()
    state = service(settings(), docker, Ports(docker, [BOLT, OLLAMA])).ensure(print)
    assert state.ready and docker.commands == []


def test_only_the_missing_services_are_started_with_compose() -> None:
    docker = Docker()
    docker_services = service(settings(), docker, Ports(docker, [OLLAMA]))
    state = docker_services.ensure(print)
    up = docker.composed("up")
    assert state.ready and len(up) == 1
    assert up[0][-3:] == ["up", "--detach", "neo4j"]
    assert docker_services.started == ["neo4j"]


def test_neo4j_and_ollama_missing_are_started_together() -> None:
    docker = Docker()
    docker_services = service(settings(), docker)
    assert docker_services.ensure(print).ready
    assert docker.composed("up")[0][-2:] == ["neo4j", "ollama"]
    assert docker_services.started == ["neo4j", "ollama"]


def test_compose_uses_the_project_and_the_gpu_file() -> None:
    docker = Docker()
    service(settings(), docker).ensure(print)
    up = docker.composed("up")[0]
    assert up[:4] == ["docker", "compose", "--project-name", "prueba-chunking"]
    assert up[4:8] == ["-f", "/repo/docker/compose.yaml", "-f", "/repo/docker/compose.amd.yaml"]
    cpu = Docker()
    service(settings(gpu="cpu"), cpu).ensure(print)
    assert "/repo/docker/compose.amd.yaml" not in cpu.composed("up")[0]
    assert "/repo/docker/compose.cpu.yaml" not in cpu.composed("up")[0]


def test_the_environment_has_the_ports_and_the_groups_of_the_gpu() -> None:
    docker = Docker()
    service(settings(), docker).ensure(print)
    env = docker.envs[docker.commands.index(docker.composed("up")[0])]
    assert env is not None
    assert env["NEO4J_BOLT_PORT"] == "7688" and env["OLLAMA_PORT"] == "11434"
    assert env["NEO4J_HTTP_PORT"] == "7475" and env["NEO4J_VOLUME"] == "prueba-chunking-neo4j-data"
    assert env["VIDEO_GID"] == "985" and env["RENDER_GID"] == "989"


def test_the_password_goes_only_in_the_environment_of_compose_up() -> None:
    docker = Docker()
    service(settings(), docker).ensure(print)
    with_auth = [env for env in docker.envs if env and "NEO4J_AUTH" in env]
    assert with_auth == [docker.envs[docker.commands.index(docker.composed("up")[0])]]
    assert with_auth[0]["NEO4J_AUTH"] == "neo4j/secreta123"
    assert not any("secreta123" in part for command in docker.commands for part in command)


def test_run_command_adds_the_environment_to_the_inherited_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INHERITED", "yes")
    command = [sys.executable, "-c", "import os; print(os.environ['INHERITED'], os.environ['SECRET'])"]
    assert services.run_command(command, {"SECRET": "s"}).stdout.strip() == "yes s"


def test_a_daemon_that_comes_up_is_waited_for() -> None:
    docker = Docker(daemon_down=3)
    clock = Clock()
    said: list[str] = []
    state = service(settings(), docker, clock=clock).ensure(said.append)
    assert state.ready and docker.composed("up")
    assert "sudo systemctl start docker" in said[0]
    assert any("ya responde" in line for line in said)
    assert clock.now >= 3


def test_a_daemon_that_never_answers_gives_up_without_compose() -> None:
    docker = Docker(daemon_down=None)
    clock = Clock()
    state = service(settings(), docker, clock=clock).ensure(print)
    assert not state.ready and "systemctl" in state.detail
    assert clock.now >= DAEMON_TIMEOUT
    assert docker.composed("up") == []


def test_the_old_standalone_container_is_removed_keeping_its_volume() -> None:
    docker = Docker(old="")
    service(settings(), docker).ensure(print)
    verbs = [c[1] for c in docker.commands]
    assert ["docker", "rm", "prueba-chunking-neo4j"] in docker.commands  # without --volumes
    assert verbs.index("rm") < docker.commands.index(docker.composed("up")[0])


def test_a_running_old_container_is_never_touched() -> None:
    docker = Docker(old="", old_running=True)
    state = service(settings(), docker, Ports(docker, [OLLAMA])).ensure(print)
    assert not state.ready and "docker stop prueba-chunking-neo4j" in state.detail
    assert all(c[1] not in ("stop", "rm") for c in docker.commands) and docker.composed("up") == []


def test_a_container_of_the_compose_project_is_not_migrated() -> None:
    docker = Docker(old="prueba-chunking")
    service(settings(), docker).ensure(print)
    assert all(c[1] not in ("stop", "rm") for c in docker.commands)


def test_what_was_already_running_is_not_counted_as_started() -> None:
    docker = Docker(running=["neo4j"])
    docker_services = service(settings(), docker, Ports(docker, [OLLAMA]))
    docker_services.ensure(print)
    assert docker_services.started == []


def test_on_exit_only_what_it_started_is_stopped() -> None:
    docker = Docker(running=["ollama"])  # running but not answering yet: not ours
    watched = Watched()
    docker_services = service(settings(), docker, watch=watched)
    docker_services.ensure(print)
    assert docker_services.started == ["neo4j"]
    assert watched.commands[0][-2:] == ["stop", "neo4j"]
    docker_services.stop(print)
    stop = docker.composed("stop")
    assert len(stop) == 1 and stop[0][-2:] == ["stop", "neo4j"]
    assert watched.released and docker_services.started == []


def test_keep_docker_leaves_them_running() -> None:
    docker = Docker()
    watched = Watched()
    docker_services = service(settings(keep=True), docker, watch=watched)
    docker_services.ensure(print)
    docker_services.stop(print)
    assert docker.composed("stop") == [] and watched.commands == []


def test_nothing_started_nothing_stopped() -> None:
    docker = Docker()
    docker_services = service(settings(), docker, Ports(docker, [BOLT, OLLAMA]))
    docker_services.ensure(print)
    docker_services.stop(print)
    assert docker.commands == []


def test_without_a_valid_password_neo4j_needs_its_volume() -> None:
    docker = Docker()
    state = service(settings(password="corta"), docker, Ports(docker, [OLLAMA])).ensure(print)
    assert not state.ready and "8 caracteres o más" in state.detail
    assert docker.composed("up") == []
    with_volume = Docker(volume=True)
    assert service(settings(password="corta"), with_volume, Ports(with_volume, [OLLAMA])).ensure(print).ready


def test_ollama_alone_does_not_block() -> None:
    docker = Docker()
    state = service(settings(), docker, Ports(docker, [BOLT])).ensure(print)
    assert state.ready and docker.composed("up")[0][-1] == "ollama"


def test_a_failed_compose_up_says_why() -> None:
    docker = Docker(up_fails=True)
    docker_services = service(settings(), docker)
    state = docker_services.ensure(print)
    assert not state.ready and "port is already allocated" in state.detail
    assert docker_services.started == []


def test_remote_disabled_or_missing_docker_is_never_run() -> None:
    for config, docker in [
        (settings(url="neo4j://graph.example:7687", ollama="http://llm.example:11434"), Docker()),
        (settings(docker=False), Docker()),
        (settings(), Docker(installed=False)),
    ]:
        state = service(config, docker).ensure(print)
        assert not state.ready and docker.commands == []


def test_a_neo4j_that_never_answers_times_out() -> None:
    docker = Docker()
    clock = Clock()
    state = service(settings(), docker, Ports(docker, [OLLAMA], opens=False), clock).ensure(print)
    assert not state.ready and "no respondió" in state.detail
    assert clock.now >= NEO4J_TIMEOUT


def test_the_browser_port_goes_next_to_the_bolt_port() -> None:
    assert services.http_port(7687) == 7474 and services.http_port(17687) == 17474
    assert services.http_port(100) == 7474


def test_the_watchdog_runs_its_command_only_if_not_released(tmp_path: Path) -> None:
    mark = tmp_path / "stopped"
    command = [sys.executable, "-c", f"open({str(mark)!r}, 'w').close()"]
    assert not docker_watchdog.watch(command, "done\n") and not mark.exists()
    assert docker_watchdog.watch(command, "") and mark.exists()


def test_the_compose_file_has_both_services_and_keeps_the_old_volume() -> None:
    compose = (Path(__file__).parents[3] / "docker" / "compose.yaml").read_text()
    assert "name: prueba-chunking\n" in compose
    assert "  neo4j:\n" in compose and "  ollama:\n" in compose
    assert "prueba-chunking-neo4j-data}" in compose and "- NEO4J_AUTH\n" in compose


def test_the_neo4j_browser_uses_the_http_port_published_next_to_the_bolt() -> None:
    def ps(command: Sequence[str], env: Mapping[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        ports = "0.0.0.0:17474->7474/tcp, 0.0.0.0:17687->7687/tcp\n0.0.0.0:7474->7474/tcp, 0.0.0.0:7687->7687/tcp\n"
        return subprocess.CompletedProcess(command, 0, ports, "")

    url = neo4j_browser(settings(url="neo4j://localhost:17687"), run=ps)
    assert url.startswith("http://localhost:17474/browser/?dbms=neo4j%3A%2F%2Fneo4j%40localhost%3A17687")
    assert neo4j_browser(settings(url="neo4j://localhost:9999"), run=ps).startswith("http://localhost:7474/")
