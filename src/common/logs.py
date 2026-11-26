"""The logs of the server: configured in one place (`configure_logging`, called by `serve`); every module only asks
for its logger with `logging.getLogger(__name__)`. The console draws on the terminal, so it keeps them off the screen
(`quiet_logging`): what its server says goes to the server's own output."""

import logging
from collections.abc import Sequence
from typing import TextIO

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
LOG_LEVEL = "INFO"
_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_DATE = "%Y-%m-%dT%H:%M:%S%z"
_MASK = "***"
_MAX_TEXT = 200  # an error can quote what it was given: only this much of it reaches a log
# They speak per request or per page, and may repeat what they read: only their warnings and errors.
_TALKATIVE = ("httpx", "httpcore", "docling", "docling_core", "docling_ibm_models", "transformers")


class _Masking(logging.Formatter):
    """Formats a line, tracebacks included, without its secrets."""

    def __init__(self, secrets: Sequence[str]) -> None:
        super().__init__(_FORMAT, _DATE)
        self._secrets = [s for s in secrets if s]

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        for secret in self._secrets:
            line = line.replace(secret, _MASK)
        return line


def configure_logging(level: str = LOG_LEVEL, secrets: Sequence[str] = (), stream: TextIO | None = None) -> None:
    """Sends the logs to `stream` (stderr by default). Uvicorn keeps its own loggers and format."""
    handler = logging.StreamHandler(stream)
    handler.setFormatter(_Masking(secrets))
    logging.basicConfig(level=level, handlers=[handler], force=True)
    for name in _TALKATIVE:
        logging.getLogger(name).setLevel(logging.WARNING)


def quiet_logging() -> None:
    """Without a handler, Python prints warnings to stderr: that would write over the console's screen."""
    logging.getLogger().addHandler(logging.NullHandler())


def brief(text: str) -> str:
    """A text from outside (an error, a file name) fit for a log: one line, so it can't forge another, and short, so
    an error quoting a document doesn't copy it."""
    line = " ".join(text.split())
    return line if len(line) <= _MAX_TEXT else f"{line[:_MAX_TEXT]}..."
