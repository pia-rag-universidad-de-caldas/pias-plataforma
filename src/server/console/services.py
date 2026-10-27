"""What the console starts: Neo4j (a Docker container) when it doesn't answer, and always its own single server (a
child process that lives exactly as long as the console). A Neo4j that already answers is used as it is.
"""

import ctypes
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO
from urllib.parse import quote, urlsplit

from .settings import NEO4J_HTTP_PORT, ConsoleSettings

NEO4J_TIMEOUT = 120.0  # seconds for a started container to accept connections (the first run creates its database)
PASSWORD_MIN = 8  # Neo4j refuses a shorter initial password
POLL = 1.0
PR_SET_PDEATHSIG = 1  # prctl option (linux/prctl.h)

type CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]
type Probe = Callable[[str, int], bool]
type Report = Callable[[str], None]


def run_command(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(command), capture_output=True, text=True, check=False)


def port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


@dataclass(frozen=True)
class Neo4jState:
    ready: bool
    detail: str


class Neo4jService:
    """Makes sure Neo4j answers at the settings' bolt address, starting or creating its Docker container if needed."""

    def __init__(
        self,
        settings: ConsoleSettings,
        run: CommandRunner = run_command,
        probe: Probe = port_open,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._run = run
        self._probe = probe
        self._sleep = sleep
        self._clock = clock

    def _docker(self, *arguments: str) -> subprocess.CompletedProcess[str] | None:
        """The result of `docker <arguments>`, or None if docker isn't installed."""
        try:
            return self._run(["docker", *arguments])
        except OSError:
            return None

    def _create_command(self, port: int) -> list[str]:
        s = self._settings
        return [
            "run",
            "--detach",
            "--name",
            s.container,
            "--publish",
            f"{port}:7687",
            "--publish",
            f"{NEO4J_HTTP_PORT}:7474",
            "--env",
            f"NEO4J_AUTH={s.neo4j_user}/{s.neo4j_password}",
            "--volume",
            f"{s.volume}:/data",
            s.image,
        ]

    def _wait(self, host: str, port: int, report: Report) -> Neo4jState:
        report(f"Esperando a Neo4j en {host}:{port}...")
        deadline = self._clock() + NEO4J_TIMEOUT
        while self._clock() < deadline:
            if self._probe(host, port):
                return Neo4jState(True, f"Neo4j responde en {host}:{port} (contenedor {self._settings.container})")
            self._sleep(POLL)
        return Neo4jState(False, f"Neo4j no respondió en {host}:{port} después de {NEO4J_TIMEOUT:.0f} s")

    def ensure(self, report: Report) -> Neo4jState:
        s = self._settings
        host, port = s.bolt_address
        if self._probe(host, port):
            return Neo4jState(True, f"Neo4j ya responde en {host}:{port}")
        if not s.docker:
            return Neo4jState(False, f"Neo4j no responde en {host}:{port} (Docker desactivado)")
        if not s.is_local(host):
            return Neo4jState(False, f"Neo4j no responde en {host}:{port} y no es local: no se arranca")
        found = self._docker("container", "inspect", "--format", "{{.State.Running}}", s.container)
        if found is None:
            return Neo4jState(False, f"Neo4j no responde en {host}:{port} y docker no está instalado")
        if found.returncode == 0:
            if found.stdout.strip() != "true":
                report(f"Arrancando el contenedor {s.container}...")
                started = self._docker("start", s.container)
                if started is None or started.returncode != 0:
                    error = started.stderr.strip() if started else "docker failed"
                    return Neo4jState(False, f"docker start {s.container}: {error}")
            return self._wait(host, port, report)
        if s.neo4j_password is None or len(s.neo4j_password) < PASSWORD_MIN:
            return Neo4jState(
                False,
                f"Neo4j no responde en {host}:{port}; crear su contenedor necesita una clave de "
                f"{PASSWORD_MIN} caracteres o más (NEO4J_PASSWORD)",
            )
        report(f"Creando el contenedor {s.container} ({s.image}) en el puerto {port}...")
        created = self._docker(*self._create_command(port))
        if created is None or created.returncode != 0:
            error = created.stderr.strip() if created else "docker failed"
            return Neo4jState(False, f"docker run {s.image}: {error}")
        return self._wait(host, port, report)


def _die_with_parent() -> None:
    """In the child, before running serve: on Linux, the kernel sends it SIGTERM if the console dies in any way
    (even `kill -9`), so a server never outlives its console."""
    if sys.platform == "linux":
        ctypes.CDLL(None, use_errno=True).prctl(PR_SET_PDEATHSIG, signal.SIGTERM)


def neo4j_browser(settings: ConsoleSettings, run: CommandRunner = run_command) -> str:
    """The Neo4j Browser's URL for the settings' bolt: its HTTP port is the one Docker publishes next to that bolt port
    (17474 next to 17687), or the default 7474; the Browser opens already pointing at the bolt and user."""
    host, port = settings.bolt_address
    http_port = NEO4J_HTTP_PORT
    try:
        listing = run(["docker", "ps", "--format", "{{.Ports}}"])
    except OSError:
        listing = None
    for line in listing.stdout.splitlines() if listing and listing.returncode == 0 else []:
        if re.search(rf":{port}->7687/tcp", line):
            published = re.search(r":(\d+)->7474/tcp", line)
            if published:
                http_port = int(published.group(1))
                break
    scheme = urlsplit(settings.neo4j_url).scheme or "neo4j"
    target = quote(f"{scheme}://{settings.neo4j_user}@{host}:{port}", safe="")
    return f"http://{host}:{http_port}/browser/?dbms={target}&connectURL={target}"


def open_url(url: str) -> bool:
    """Opens the URL in the browser without writing on the console's screen."""
    opener = shutil.which("xdg-open") or shutil.which("open")
    if opener is None:
        return webbrowser.open(url)
    subprocess.Popen([opener, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    return True


class ServerProcess:
    """`python -m server serve` in the background, its output in a log file; stopped with the console."""

    def __init__(self, settings: ConsoleSettings, log: str) -> None:
        self._settings = settings
        self._log = Path(log)
        self._process: subprocess.Popen[bytes] | None = None
        self._output: IO[bytes] | None = None

    @property
    def log(self) -> str:
        return str(self._log)

    def command(self) -> list[str]:
        s = self._settings
        host, port = s.server_address
        return [
            sys.executable,
            "-m",
            "server",
            "serve",
            "--host",
            host,
            "--port",
            str(port),
            "--neo4j-url",
            s.neo4j_url,
            "--neo4j-user",
            s.neo4j_user,
            "--neo4j-database",
            s.neo4j_database,
            *s.serve_options,
        ]

    def start(self) -> None:
        environment = dict(os.environ)
        environment.pop("NEO4J_PASSWORD", None)
        if self._settings.neo4j_password:
            environment["NEO4J_PASSWORD"] = self._settings.neo4j_password
        self._log.parent.mkdir(parents=True, exist_ok=True)
        self._output = self._log.open("wb")
        # Without a console on stdin, serve never prompts for the password: it starts with /data in 503 instead.
        self._process = subprocess.Popen(
            self.command(),
            stdin=subprocess.DEVNULL,
            stdout=self._output,
            stderr=subprocess.STDOUT,
            env=environment,
            preexec_fn=_die_with_parent,
        )

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def tail(self, lines: int = 15) -> str:
        """The last lines of the server's output (why it didn't start)."""
        try:
            return "\n".join(self._log.read_text(errors="replace").splitlines()[-lines:])
        except OSError:
            return ""

    def stop(self) -> None:
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
        if self._output is not None:
            self._output.close()
        self._process = self._output = None
