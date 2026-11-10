"""common.logs: one place configures the logs of `serve`; what they say is one line and never a secret."""

import io
import logging
from collections.abc import Iterator

import pytest

from common.logs import brief, configure_logging, quiet_logging


@pytest.fixture(autouse=True)
def root_as_it_was() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


def test_a_line_says_when_how_bad_where_and_what() -> None:
    stream = io.StringIO()
    configure_logging("INFO", stream=stream)
    logging.getLogger("chunking.api").info("run %s started", "r1")
    assert stream.getvalue().split(" ", 1)[1] == "INFO chunking.api: run r1 started\n"
    assert stream.getvalue()[:4].isdigit()


def test_below_the_level_nothing_is_written() -> None:
    stream = io.StringIO()
    configure_logging("WARNING", stream=stream)
    logging.getLogger("chunking.api").info("run started")
    assert stream.getvalue() == ""


@pytest.mark.parametrize("name", ["httpx", "httpcore", "docling", "transformers"])
def test_what_libraries_say_of_each_request_or_page_is_left_out(name: str) -> None:
    stream = io.StringIO()
    configure_logging("INFO", stream=stream)
    logging.getLogger(name).info("HTTP Request: POST /data/batch")
    assert stream.getvalue() == ""


def test_a_secret_never_reaches_the_log() -> None:
    stream = io.StringIO()
    configure_logging("INFO", secrets=("s3cret",), stream=stream)
    logging.getLogger("data").warning("could not log in with %s", "s3cret")
    assert "s3cret" not in stream.getvalue()
    assert "***" in stream.getvalue()


def test_a_secret_in_a_traceback_never_reaches_the_log() -> None:
    stream = io.StringIO()
    configure_logging("INFO", secrets=("s3cret",), stream=stream)
    try:
        raise ValueError("bolt://neo4j:s3cret@localhost")
    except ValueError:
        logging.getLogger("data").exception("the graph failed")
    assert "s3cret" not in stream.getvalue()


def test_no_secret_given_changes_nothing() -> None:
    stream = io.StringIO()
    configure_logging("INFO", secrets=("",), stream=stream)
    logging.getLogger("data").warning("as it is")
    assert stream.getvalue().endswith("data: as it is\n")


def test_brief_keeps_a_short_text() -> None:
    assert brief("the file is corrupt") == "the file is corrupt"


def test_brief_leaves_one_line() -> None:
    assert brief("first\nforged line\r\n  last") == "first forged line last"


def test_brief_cuts_what_is_long_and_says_so() -> None:
    cut = brief("x" * 5000)
    assert len(cut) < 300
    assert cut.endswith("...")


def test_without_configuring_a_warning_is_not_printed_when_quiet(capsys: pytest.CaptureFixture[str]) -> None:
    root = logging.getLogger()
    root.handlers[:] = []
    quiet_logging()
    logging.getLogger("console").warning("this would break the screen")
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == ""
