"""HttpNotifier (feature 040): checks the destination again when it sends, and never raises."""

from collections.abc import Sequence

import httpx
import pytest

from pipeline.adapters.http import notifier
from pipeline.adapters.http.notifier import HttpNotifier
from pipeline.domain.callbacks import allowed_hosts
from pipeline.models import Actor

URL = "http://lab.local/hook"
HOSTS = allowed_hosts("lab.local")


def resolving_to(*addresses: str) -> notifier.Resolver:
    def resolve(_: str, __: int | None) -> Sequence[str]:
        return addresses

    return resolve


def forbid_sending(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    sent: list[str] = []

    def post(url: str, **_: object) -> httpx.Response:
        sent.append(url)
        return httpx.Response(200)

    monkeypatch.setattr(httpx, "post", post)
    return sent


def test_an_allowed_host_that_resolves_to_a_forbidden_address_is_not_called(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = forbid_sending(monkeypatch)
    error = HttpNotifier(hosts=HOSTS, resolve=resolving_to("169.254.169.254")).notify(Actor("lab", URL), {})
    assert sent == [] and "forbidden" in (error or "")


def test_a_destination_no_longer_allowed_is_not_called(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = forbid_sending(monkeypatch)
    error = HttpNotifier(hosts=allowed_hosts(None), resolve=resolving_to("10.0.0.5")).notify(Actor("lab", URL), {})
    assert sent == [] and "allowed" in (error or "")


def test_a_name_that_does_not_resolve_is_an_error_not_an_exception() -> None:
    def resolve(_: str, __: int | None) -> Sequence[str]:
        raise OSError("no such host")

    assert "no such host" in (HttpNotifier(hosts=HOSTS, resolve=resolve).notify(Actor("lab", URL), {}) or "")


def test_a_notice_goes_to_an_allowed_destination_without_following_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: dict[str, object] = {}

    def post(url: str, **options: object) -> httpx.Response:
        asked.update(options, url=url)
        return httpx.Response(200)

    monkeypatch.setattr(httpx, "post", post)
    assert HttpNotifier(hosts=HOSTS, resolve=resolving_to("10.0.0.5")).notify(Actor("lab", URL), {"a": 1}) is None
    assert asked["url"] == URL and asked["follow_redirects"] is False


def test_a_redirect_is_reported_as_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "post", lambda *_, **__: httpx.Response(302))
    error = HttpNotifier(hosts=HOSTS, resolve=resolving_to("10.0.0.5")).notify(Actor("lab", URL), {})
    assert "302" in (error or "")


def test_an_invalid_url_from_httpx_is_an_error_not_an_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    def post(*_: object, **__: object) -> httpx.Response:
        raise httpx.InvalidURL("bad")

    monkeypatch.setattr(httpx, "post", post)
    assert HttpNotifier(hosts=HOSTS, resolve=resolving_to("10.0.0.5")).notify(Actor("lab", URL), {}) is not None


def test_an_actor_without_url_needs_nothing() -> None:
    assert HttpNotifier(hosts=HOSTS, resolve=resolving_to()).notify(Actor("lab"), {}) is None


def test_the_hosts_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PIPELINE_CALLBACK_HOSTS", "lab.local")
    assert "lab.local" in notifier.callback_hosts()
