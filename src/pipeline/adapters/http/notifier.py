"""HttpNotifier: tells an actor (POST to its callback_url) that a stage is waiting for it. No retries: if it fails,
the stage is still in the inbox. The destination is checked again here, resolving its name (it may point elsewhere by
now), and a redirect isn't followed: it could lead anywhere."""

import os
import socket
from collections.abc import Callable, Sequence
from urllib.parse import urlsplit

import httpx

from pipeline.config import CALLBACK_HOSTS_VARIABLE, HTTP_TIMEOUT
from pipeline.domain.callbacks import address_problem, allowed_hosts, url_problem
from pipeline.models import Actor, JsonObject, Notifier

type Resolver = Callable[[str, int | None], Sequence[str]]


def callback_hosts() -> frozenset[str]:
    """The hosts a callback may go to: those of the configuration and those of its environment variable."""
    return allowed_hosts(os.environ.get(CALLBACK_HOSTS_VARIABLE))


def _resolve(host: str, port: int | None) -> Sequence[str]:
    return [str(found[4][0]) for found in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]


class HttpNotifier(Notifier):
    def __init__(
        self,
        timeout: float = HTTP_TIMEOUT,
        hosts: frozenset[str] | None = None,
        resolve: Resolver = _resolve,
    ) -> None:
        self._timeout = timeout
        self._hosts = callback_hosts() if hosts is None else hosts
        self._resolve = resolve

    def _destination_problem(self, url: str) -> str | None:
        problem = url_problem(url, self._hosts)
        if problem is not None:
            return problem
        parts = urlsplit(url)
        try:
            addresses = self._resolve(parts.hostname or "", parts.port)
        except (OSError, UnicodeError) as error:
            return str(error)
        return next((p for p in map(address_problem, addresses) if p is not None), None)

    def notify(self, actor: Actor, payload: JsonObject) -> str | None:
        url = actor.callback_url
        if not url:
            return None
        problem = self._destination_problem(url)
        if problem is not None:
            return f"{url}: {problem}"
        try:
            response = httpx.post(url, json=payload, timeout=self._timeout, follow_redirects=False)
        except (httpx.HTTPError, httpx.InvalidURL) as e:
            return f"{url}: {e}"
        return None if response.is_success else f"{url}: {response.status_code}"
