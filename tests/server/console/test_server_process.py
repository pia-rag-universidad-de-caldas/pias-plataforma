"""The console's server process: it lives as long as the console, in Linux and in Windows."""

import ctypes
import subprocess
import sys
from pathlib import Path

import pytest

from server.console import server_process as services
from server.console.server_process import ServerProcess
from server.console.settings import ConsoleSettings


def settings(
    url: str = "neo4j://localhost:7688", password: str | None = "secreta123", docker: bool = True
) -> ConsoleSettings:
    return ConsoleSettings("http://127.0.0.1:8000", url, "neo4j", "neo4j", password, docker=docker)


class Started:
    """Stands in for subprocess.Popen: records what the server was started with."""

    options: dict[str, object] = {}  # noqa: RUF012 (reset by the fixture, read by each test)
    pid = 4321

    def __init__(self, _: list[str], **options: object) -> None:
        Started.options = options


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """The fake Popen, plus the pids handed to the Windows job."""
    joined: list[int] = []
    monkeypatch.setattr(subprocess, "Popen", Started)
    monkeypatch.setattr(services, "_die_with_console", joined.append)
    return joined


def test_on_windows_the_server_starts_without_preexec_fn_and_joins_the_job(
    started: list[int], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    ServerProcess(settings(), str(tmp_path / "server.log")).start()
    assert Started.options["preexec_fn"] is None
    assert started == [Started.pid]


def test_on_linux_the_server_dies_with_its_parent_and_there_is_no_job(
    started: list[int], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    ServerProcess(settings(), str(tmp_path / "server.log")).start()
    assert Started.options["preexec_fn"] is services._die_with_parent
    assert started == []


@pytest.mark.skipif(ctypes.sizeof(ctypes.c_void_p) != 8, reason="the size below is the 64-bit one")
def test_the_job_limits_have_the_size_windows_expects() -> None:
    assert ctypes.sizeof(services._JobLimits) == 144
