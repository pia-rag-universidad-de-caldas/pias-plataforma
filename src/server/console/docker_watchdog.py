"""`python -m server.console.docker_watchdog <command...>` (feature 054): waits on its stdin, a pipe from the console.
If the console writes "done" it cleaned up by itself and this leaves; if the pipe closes without it (the console died,
even with `kill -9`), it runs the command: `docker compose stop` of what the console started."""

import subprocess
import sys

RELEASED = "done"


def watch(command: list[str], received: str) -> bool:
    """Runs `command` unless the console released it; whether it ran."""
    if received.strip() == RELEASED or not command:
        return False
    subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    return True


def main() -> int:
    try:
        received = sys.stdin.read()
    except (OSError, KeyboardInterrupt):
        received = ""
    watch(sys.argv[1:], received)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
