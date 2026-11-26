"""Neo4j and Ollama for the console (features 034 and 054): the services of the Docker Compose project in
docker/compose.yaml, started when they don't answer and are local; one that already answers is used as it is.

The console stops on exit only what it started (`docker compose stop <those>`), unless --keep-docker. If the console
dies without cleaning up (even `kill -9`), a watchdog (docker_watchdog.py) stops them when its pipe closes.
"""

import os
import re
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote, urlsplit

from .settings import BOLT_PORT, NEO4J_HTTP_PORT, ConsoleSettings

NEO4J_TIMEOUT = 120.0  # seconds for a started Neo4j to accept connections (the first run creates its database)
DAEMON_TIMEOUT = 300.0  # seconds waiting for the Docker daemon before going on without the services
DAEMON_REMINDER = 15.0  # seconds between two reminders that the daemon is still down
PASSWORD_MIN = 8  # Neo4j refuses a shorter initial password
POLL = 1.0
NEO4J_AUTH = "NEO4J_AUTH"  # the variable of Neo4j's image with its user and initial password
NEO4J, OLLAMA = "neo4j", "ollama"  # the services of docker/compose.yaml
COMPOSE_PROJECT_LABEL = "com.docker.compose.project"
# Bolt's magic number and four versions asked for (5.x down to 4.x): the server answers with 4 bytes.
BOLT_HANDSHAKE = bytes.fromhex("6060b017 00080805 00000404 00000304 00000104")
START_DOCKER = "sudo systemctl start docker, o abre Docker Desktop (systemctl --user start docker-desktop)"


class CommandRunner(Protocol):
    def __call__(
        self, command: Sequence[str], env: Mapping[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Runs `command` with `env` added to the environment it inherits."""
        ...


class Watch(Protocol):
    def release(self) -> None:
        """The console cleaned up by itself: the watchdog leaves without doing anything."""
        ...


type Probe = Callable[[str, int], bool]
type Report = Callable[[str], None]
type Watcher = Callable[[Sequence[str], Mapping[str, str]], Watch | None]
type GroupId = Callable[[str], int | None]


def run_command(command: Sequence[str], env: Mapping[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, **env} if env else None
    return subprocess.run(list(command), capture_output=True, text=True, check=False, env=environment)


def port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def bolt_answers(host: str, port: int) -> bool:
    """Whether Neo4j itself answers the bolt handshake: an open port isn't enough (Docker Desktop opens it at once,
    while Neo4j is still starting). Any version in the answer, even "none", is Neo4j answering."""
    try:
        with socket.create_connection((host, port), timeout=2.0) as connection:
            connection.sendall(BOLT_HANDSHAKE)
            return len(connection.recv(4)) == 4
    except OSError:
        return False


def group_id(name: str) -> int | None:
    """The host's id of a group (video, render), or None (no such group, or not POSIX)."""
    try:
        import grp  # POSIX only

        return grp.getgrnam(name).gr_gid
    except (ImportError, KeyError):
        return None


def http_port(bolt: int) -> int:
    """The Neo4j Browser's port published next to a bolt port: as far from 7474 as the bolt is from 7687
    (17687 → 17474), or 7474 if that falls out of range."""
    port = NEO4J_HTTP_PORT + bolt - BOLT_PORT
    return port if 0 < port < 65536 else NEO4J_HTTP_PORT


class _Watchdog:
    """A process that runs `command` if the console dies without releasing it (its stdin pipe closes)."""

    def __init__(self, command: Sequence[str], env: Mapping[str, str]) -> None:
        arguments = [sys.executable, "-m", "server.console.docker_watchdog", *command]
        environment = {**os.environ, **env}
        quiet = subprocess.DEVNULL
        # Apart from the console's session (or group): closing the terminal or Ctrl+C don't reach it.
        if sys.platform == "win32":
            self._process = subprocess.Popen(
                arguments,
                stdin=subprocess.PIPE,
                stdout=quiet,
                stderr=quiet,
                env=environment,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )
        else:
            self._process = subprocess.Popen(
                arguments, stdin=subprocess.PIPE, stdout=quiet, stderr=quiet, env=environment, start_new_session=True
            )

    def release(self) -> None:
        stdin = self._process.stdin
        try:
            if stdin is not None:
                stdin.write(b"done\n")
                stdin.close()
            self._process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            self._process.kill()


def start_watchdog(command: Sequence[str], env: Mapping[str, str]) -> Watch | None:
    try:
        return _Watchdog(command, env)
    except OSError:
        return None


@dataclass(frozen=True)
class Neo4jState:
    ready: bool
    detail: str


class DockerServices:
    """Makes sure Neo4j answers at the settings' bolt address (and starts Ollama if it doesn't answer), with
    `docker compose up -d` of the missing services; remembers which ones it started, to stop only those."""

    def __init__(
        self,
        settings: ConsoleSettings,
        compose_dir: str,
        run: CommandRunner = run_command,
        probe: Probe = port_open,
        bolt: Probe | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        watch: Watcher = start_watchdog,
        groups: GroupId = group_id,
    ) -> None:
        self._settings = settings
        self._compose_dir = compose_dir
        self._run = run
        self._probe = probe  # Ollama's port
        self._bolt = bolt or (bolt_answers if probe is port_open else probe)  # Neo4j's
        self._sleep = sleep
        self._clock = clock
        self._watch = watch
        self._groups = groups
        self._watchdog: Watch | None = None
        self.started: list[str] = []  # services this console started: the only ones it stops

    def _docker(self, *arguments: str, env: Mapping[str, str] | None = None) -> subprocess.CompletedProcess[str] | None:
        """The result of `docker <arguments>`, or None if docker isn't installed."""
        try:
            return self._run(["docker", *arguments], env)
        except OSError:
            return None

    def compose(self, *arguments: str) -> list[str]:
        """`docker compose` of the project, with compose.yaml and the GPU's file, then `arguments`."""
        s = self._settings
        files = [f"{self._compose_dir}/compose.yaml"]
        if s.gpu != "cpu":
            files.append(f"{self._compose_dir}/compose.{s.gpu}.yaml")
        return [
            "docker",
            "compose",
            "--project-name",
            s.compose_project,
            *(p for f in files for p in ("-f", f)),
            *arguments,
        ]

    def environment(self) -> dict[str, str]:
        """What compose.yaml reads (ports, images, the GPU's groups); never the password."""
        s = self._settings
        environment = {
            "NEO4J_IMAGE": s.image,
            "NEO4J_BOLT_PORT": str(s.bolt_address[1]),
            "NEO4J_HTTP_PORT": str(http_port(s.bolt_address[1])),
            "NEO4J_VOLUME": s.volume,
            "OLLAMA_PORT": str(s.ollama_address[1]),
        }
        if s.gpu == "amd":
            for variable, name in (("VIDEO_GID", "video"), ("RENDER_GID", "render")):
                found = self._groups(name)
                if found is not None:
                    environment[variable] = str(found)
        return environment

    def _compose(self, *arguments: str, auth: bool = False) -> subprocess.CompletedProcess[str] | None:
        s = self._settings
        env = self.environment()
        if auth and s.neo4j_password:
            env[NEO4J_AUTH] = f"{s.neo4j_user}/{s.neo4j_password}"  # by the environment: not visible in `ps`
        try:
            return self._run(self.compose(*arguments), env)
        except OSError:
            return None

    def _daemon(self, report: Report) -> str:
        """ "" once the Docker daemon answers; otherwise why not (it waits for it up to DAEMON_TIMEOUT)."""
        found = self._docker("info", "--format", "{{.ServerVersion}}")
        if found is None:
            return "docker no está instalado"
        if found.returncode == 0:
            return ""
        report(
            f"El demonio de Docker no responde: espero a que arranque (hasta {DAEMON_TIMEOUT:.0f} s, Ctrl+C para "
            f"salir). Para arrancarlo: {START_DOCKER}"
        )
        deadline = self._clock() + DAEMON_TIMEOUT
        reminder = self._clock() + DAEMON_REMINDER
        while self._clock() < deadline:
            self._sleep(POLL)
            found = self._docker("info", "--format", "{{.ServerVersion}}")
            if found is not None and found.returncode == 0:
                report("El demonio de Docker ya responde.")
                return ""
            if self._clock() >= reminder:
                reminder = self._clock() + DAEMON_REMINDER
                report(f"Docker sigue sin responder ({START_DOCKER})...")
        return f"el demonio de Docker no respondió en {DAEMON_TIMEOUT:.0f} s ({START_DOCKER})"

    def _migrate(self, report: Report) -> str:
        """The standalone container of before (docker run, feature 034) gives way to the compose service; its volume
        is the one compose.yaml uses, so no data is lost. Never one that is running (maybe on another port): two
        Neo4j can't share a volume, so then the compose one isn't started and this says why."""
        s = self._settings
        shape = f'{{{{.State.Running}}}} {{{{index .Config.Labels "{COMPOSE_PROJECT_LABEL}"}}}}'
        found = self._docker("container", "inspect", "--format", shape, s.container)
        if found is None or found.returncode != 0:
            return ""
        running, _, project = found.stdout.strip().partition(" ")
        if project == s.compose_project:
            return ""
        if running == "true":
            return (
                f"el contenedor suelto {s.container} está corriendo (¿en otro puerto?) y usa el volumen {s.volume}: "
                f"detenlo (docker stop {s.container}) o usa su puerto (--neo4j-url)"
            )
        report(f"Pasando el contenedor suelto {s.container} al proyecto de compose (su volumen {s.volume} se queda)...")
        removed = self._docker("rm", s.container)  # without --volumes: the named volume stays
        if removed is None or removed.returncode != 0:
            error = removed.stderr.strip() if removed else "docker failed"
            return f"no se pudo quitar el contenedor suelto {s.container}: {error}"
        return ""

    def _creatable(self) -> bool:
        """Whether Neo4j can start: its volume already has a database, or there is a password for a new one."""
        s = self._settings
        if s.neo4j_password is not None and len(s.neo4j_password) >= PASSWORD_MIN:
            return True
        volume = self._docker("volume", "inspect", s.volume)
        return volume is not None and volume.returncode == 0

    def _running(self) -> set[str]:
        listed = self._compose("ps", "--status", "running", "--services")
        return set(listed.stdout.split()) if listed is not None and listed.returncode == 0 else set()

    def _wait(self, host: str, port: int, report: Report) -> Neo4jState:
        report(f"Esperando a Neo4j en {host}:{port}...")
        deadline = self._clock() + NEO4J_TIMEOUT
        while self._clock() < deadline:
            if self._bolt(host, port):
                return Neo4jState(True, f"Neo4j responde en {host}:{port} (servicio {NEO4J} de compose)")
            self._sleep(POLL)
        return Neo4jState(False, f"Neo4j no respondió en {host}:{port} después de {NEO4J_TIMEOUT:.0f} s")

    def ensure(self, report: Report) -> Neo4jState:
        """Starts what is missing and waits for Neo4j (never for Ollama: the RAG waits for it, not the console)."""
        s = self._settings
        host, port = s.bolt_address
        ollama_host, ollama_port = s.ollama_address
        wanted: list[str] = []
        state = Neo4jState(True, f"Neo4j ya responde en {host}:{port}")
        if not self._bolt(host, port):
            if not s.docker:
                state = Neo4jState(False, f"Neo4j no responde en {host}:{port} (Docker desactivado)")
            elif not s.is_local(host):
                state = Neo4jState(False, f"Neo4j no responde en {host}:{port} y no es local: no se arranca")
            else:
                wanted.append(NEO4J)
        if s.docker and not self._probe(ollama_host, ollama_port):
            if s.is_local(ollama_host):
                wanted.append(OLLAMA)
            else:
                report(f"Ollama no responde en {ollama_host}:{ollama_port} y no es local: no se arranca")
        if not wanted:
            return state
        problem = self._daemon(report)
        if problem:
            return Neo4jState(False, f"Neo4j no responde en {host}:{port}: {problem}") if NEO4J in wanted else state
        if NEO4J in wanted:
            blocked = self._migrate(report)
            if blocked:
                wanted.remove(NEO4J)
                state = Neo4jState(False, f"Neo4j no responde en {host}:{port}: {blocked}")
            elif not self._creatable():
                wanted.remove(NEO4J)
                state = Neo4jState(
                    False,
                    f"Neo4j no responde en {host}:{port}; crear su base necesita una clave de "
                    f"{PASSWORD_MIN} caracteres o más (NEO4J_PASSWORD)",
                )
        if not wanted:
            return state
        before = self._running()
        report(f"Arrancando con Docker Compose: {', '.join(wanted)} (GPU de Ollama: {s.gpu})...")
        up = self._compose("up", "--detach", *wanted, auth=True)
        if up is None or up.returncode != 0:
            error = up.stderr.strip().splitlines()[-1:] if up else ["docker failed"]
            detail = f"docker compose up {' '.join(wanted)}: {''.join(error) or 'falló'}"
            return (
                Neo4jState(False, detail) if NEO4J in wanted else Neo4jState(state.ready, f"{state.detail}; {detail}")
            )
        self.started = [name for name in wanted if name not in before]
        if self.started and not s.keep_docker:
            self._watchdog = self._watch(self.compose("stop", *self.started), self.environment())
        if OLLAMA in wanted:
            report(f"Ollama arranca en {ollama_host}:{ollama_port} (la consola no lo espera).")
        return self._wait(host, port, report) if NEO4J in wanted else state

    def stop(self, report: Report) -> None:
        """`docker compose stop` of what this console started (nothing with --keep-docker)."""
        if self.started and not self._settings.keep_docker:
            report(f"Deteniendo lo que arrancó la consola: {', '.join(self.started)}...")
            stopped = self._compose("stop", *self.started)
            if stopped is None or stopped.returncode != 0:
                report(f"Aviso: docker compose stop falló: {stopped.stderr.strip() if stopped else 'docker failed'}")
        elif self.started:
            report(f"Siguen corriendo (--keep-docker): {', '.join(self.started)}.")
        self.started = []
        if self._watchdog is not None:
            self._watchdog.release()
            self._watchdog = None


def neo4j_browser(settings: ConsoleSettings, run: CommandRunner = run_command) -> str:
    """The Neo4j Browser's URL for the settings' bolt: its HTTP port is the one Docker publishes next to that bolt port
    (17474 next to 17687), or the default 7474; the Browser opens already pointing at the bolt and user."""
    host, port = settings.bolt_address
    browser_port = NEO4J_HTTP_PORT
    try:
        listing = run(["docker", "ps", "--format", "{{.Ports}}"])
    except OSError:
        listing = None
    for line in listing.stdout.splitlines() if listing and listing.returncode == 0 else []:
        if re.search(rf":{port}->7687/tcp", line):
            published = re.search(r":(\d+)->7474/tcp", line)
            if published:
                browser_port = int(published.group(1))
                break
    scheme = urlsplit(settings.neo4j_url).scheme or "neo4j"
    target = quote(f"{scheme}://{settings.neo4j_user}@{host}:{port}", safe="")
    return f"http://{host}:{browser_port}/browser/?dbms={target}&connectURL={target}"


def open_url(url: str) -> bool:
    """Opens the URL in the browser without writing on the console's screen."""
    opener = shutil.which("xdg-open") or shutil.which("open")
    if opener is None:
        return webbrowser.open(url)
    subprocess.Popen([opener, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    return True
