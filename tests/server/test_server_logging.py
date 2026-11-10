"""`serve` configures the logs, with the Neo4j password among what they never say; the console keeps its screen."""

import argparse
import logging
from collections.abc import Iterator
from typing import Any

import pytest

from common.logs import LOG_LEVELS
from server import cli
from server.console import ConsoleSettings
from server.console import app as console_app
from server.console.client import ApiClient
from server.graph import UnavailableGraph


@pytest.fixture(autouse=True)
def root_as_it_was() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


def _serve(monkeypatch: pytest.MonkeyPatch, *options: str) -> dict[str, Any]:
    """Runs `serve` up to the server itself, which isn't started: how the logs were configured."""
    configured: dict[str, Any] = {}

    def configure(level: str, secrets: tuple[str, ...] = ()) -> None:
        configured.update(level=level, secrets=secrets)

    monkeypatch.setenv("NEO4J_PASSWORD", "s3cret")
    monkeypatch.setattr(cli, "configure_logging", configure)
    monkeypatch.setattr(cli, "open_graph", lambda _: UnavailableGraph("no graph"))
    monkeypatch.setattr(cli, "serve", lambda *_: None)
    args: argparse.Namespace = cli.create_parser().parse_args(["serve", *options])
    args.function(args)
    return configured


def test_serve_logs_at_info_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _serve(monkeypatch)["level"] == "INFO"


def test_serve_takes_the_level_it_is_asked_for(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _serve(monkeypatch, "--log-level", "DEBUG")["level"] == "DEBUG"


def test_serve_only_takes_levels_that_exist(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        cli.create_parser().parse_args(["serve", "--log-level", "LOUD"])
    assert "LOUD" in capsys.readouterr().err
    assert "INFO" in LOG_LEVELS


def test_the_password_is_among_what_the_logs_never_say(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _serve(monkeypatch)["secrets"] == ("s3cret",)


def test_the_console_keeps_logs_off_its_screen(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class Busy:
        def health(self) -> object:
            return object()

        def close(self) -> None:
            pass

    logging.getLogger().handlers[:] = []
    monkeypatch.setattr(ApiClient, "to", lambda _: Busy())
    settings = ConsoleSettings("http://s", "neo4j://n", "u", "neo4j", None, False, ())
    console_app.run_console(settings)  # something answers: it leaves right after preparing
    capsys.readouterr()
    logging.getLogger("anything").warning("would break the screen")
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == ""
