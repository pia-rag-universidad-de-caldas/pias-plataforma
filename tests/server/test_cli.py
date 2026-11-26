"""The server's command line (feature 040): what it warns about and the options of the guards."""

import pytest

from llm.config import OLLAMA_URL
from server.cli import create_parser, exposure_warning, ollama_url


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_a_local_host_has_no_warning(host: str) -> None:
    assert exposure_warning(host) is None


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.5"])
def test_any_other_host_warns_there_is_no_authentication(host: str) -> None:
    assert "authentication" in (exposure_warning(host) or "")


def test_serve_takes_several_allowed_hosts() -> None:
    args = create_parser().parse_args(["serve", "--allowed-host", "a.local", "--allowed-host", "b.local"])
    assert args.allowed_host == ["a.local", "b.local"]


def test_serve_takes_the_body_limit() -> None:
    assert create_parser().parse_args(["serve", "--max-body-bytes", "5"]).max_body_bytes == 5


def test_ollama_url_is_the_option_else_the_variable_else_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLLAMA_URL", raising=False)
    assert ollama_url(create_parser().parse_args(["serve"])) == OLLAMA_URL
    monkeypatch.setenv("OLLAMA_URL", "http://gpu:11434")
    assert ollama_url(create_parser().parse_args(["serve"])) == "http://gpu:11434"
    assert ollama_url(create_parser().parse_args(["serve", "--ollama-url", "http://other:1"])) == "http://other:1"
    assert create_parser().parse_args(["console", "--ollama-url", "http://other:1"]).ollama_url == "http://other:1"
