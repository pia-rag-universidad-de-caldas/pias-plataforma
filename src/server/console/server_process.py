"""The console's own single server: a child process that lives exactly as long as the console."""

import ctypes
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import IO

from .settings import ConsoleSettings

PR_SET_PDEATHSIG = 1  # prctl option (linux/prctl.h)
JOB_EXTENDED_LIMITS = 9  # JobObjectExtendedLimitInformation (winnt.h)
JOB_KILL_ON_CLOSE = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
PROCESS_JOB_ACCESS = 0x0101  # PROCESS_SET_QUOTA | PROCESS_TERMINATE, what assigning a process to a job asks for


def _die_with_parent() -> None:
    """In the child, before running serve (Linux only): the kernel sends it SIGTERM if the console dies in any way
    (even `kill -9`), so a server never outlives its console."""
    ctypes.CDLL(None, use_errno=True).prctl(PR_SET_PDEATHSIG, signal.SIGTERM)


class _JobLimits(ctypes.Structure):
    """JOBOBJECT_EXTENDED_LIMIT_INFORMATION (winnt.h), with its two nested structures written out."""

    _fields_ = (
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
        ("IoInfo", ctypes.c_uint64 * 6),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    )


def _die_with_console(pid: int) -> None:
    """Windows' version of _die_with_parent: the process joins a job that Windows kills when its last handle closes.
    That handle is never closed here on purpose: it closes when the console dies in any way (even a closed window or
    the Task Manager). Best effort: if a call fails, the server is still stopped when the console leaves normally."""
    if sys.platform == "win32":
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.CreateJobObjectW.restype = ctypes.c_void_p
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.SetInformationJobObject.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32)
        kernel32.AssignProcessToJobObject.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
        job = kernel32.CreateJobObjectW(None, None)
        limits = _JobLimits(LimitFlags=JOB_KILL_ON_CLOSE)
        kernel32.SetInformationJobObject(job, JOB_EXTENDED_LIMITS, ctypes.byref(limits), ctypes.sizeof(limits))
        process = kernel32.OpenProcess(PROCESS_JOB_ACCESS, False, pid)
        kernel32.AssignProcessToJobObject(job, process)
        kernel32.CloseHandle(process)


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
            preexec_fn=_die_with_parent if sys.platform == "linux" else None,  # Windows refuses any preexec_fn
        )
        if sys.platform == "win32":
            _die_with_console(self._process.pid)

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
