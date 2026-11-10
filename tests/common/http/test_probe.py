"""responds: whether a route of the server answers, as a yes or no."""

import httpx
import pytest

from common.http import responds


@pytest.mark.parametrize(("status", "expected"), [(200, True), (503, False), (404, False)])
def test_only_a_success_counts_as_answering(monkeypatch: pytest.MonkeyPatch, status: int, expected: bool) -> None:
    asked: list[str] = []

    def get(url: str, timeout: float) -> httpx.Response:
        asked.append(url)
        return httpx.Response(status)

    monkeypatch.setattr(httpx, "get", get)
    assert responds("http://s/", "/data/health") is expected
    assert asked == ["http://s/data/health"]


def test_a_server_that_doesnt_answer_is_a_no(monkeypatch: pytest.MonkeyPatch) -> None:
    def get(url: str, timeout: float) -> httpx.Response:
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "get", get)
    assert responds("http://s", "/data/health") is False
