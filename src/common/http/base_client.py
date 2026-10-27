"""The base of every HTTP client of the modules (features 026 and 033): one module's routes under a path, on a shared
httpx.Client. Sending, the status → error rules and reading JSON live only here; each client adds its routes and says,
with its ErrorPolicy, which of its own exceptions to raise."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

type QueryParams = tuple[tuple[str, str | int], ...]
type Json = Any  # a decoded JSON answer of another module (checked where it is read)

NOT_FOUND = 404
CONFLICT = 409


@dataclass(frozen=True)
class ErrorPolicy:
    """How a client reports the other module: `unavailable` for network, timeout, 5xx or an answer that isn't JSON
    (the module is down: it stops a run); `rejected` for a 4xx other than 404 (it refused what was sent)."""

    service: str
    unavailable: type[Exception]
    rejected: type[Exception]


def detail(response: httpx.Response) -> str:
    """The error message of a module's answer ({"detail"} in data and chunking, {"detalle"} in ingesta)."""
    try:
        body: Json = response.json()
    except ValueError:
        return response.text[:300] or response.reason_phrase
    if isinstance(body, Mapping):
        for key in ("detail", "detalle"):
            if key in body:
                return str(body[key])
    return str(body)[:300]


def segment(value: str) -> str:
    """A value (an id, a sha256) as one segment of a route."""
    return quote(value, safe="")


class BaseHttpClient:
    """`path` is the module's prefix on the server (/ingesta, /data, /chunking); routes are relative to it."""

    def __init__(self, client: httpx.Client, path: str, errors: ErrorPolicy) -> None:
        self._client = client
        self._path = path.rstrip("/")
        self._errors = errors

    def _send(self, method: str, route: str, params: QueryParams | None = None, body: object = None) -> httpx.Response:
        """The answer, with network errors and 5xx raised as `unavailable` (the 4xx are left to the caller)."""
        url = f"{self._path}{route}"
        try:
            response = self._client.request(method, url, params=params, json=body)
        except httpx.TimeoutException as e:
            raise self._errors.unavailable(f"{method} {url}: no answer within {self._client.timeout.read}s") from e
        except httpx.HTTPError as e:
            raise self._errors.unavailable(f"{method} {url}: {e}") from e
        if response.is_server_error:
            raise self._errors.unavailable(f"{method} {url}: {response.status_code} {detail(response)}")
        return response

    def _request(
        self,
        method: str,
        route: str,
        params: QueryParams | None = None,
        body: object = None,
        not_found: type[Exception] | None = None,
    ) -> httpx.Response | None:
        """A successful answer; on 404, None, or `not_found` with the module's message if given; another 4xx is
        `rejected`."""
        response = self._send(method, route, params, body)
        if response.status_code == NOT_FOUND:
            if not_found is None:
                return None
            raise not_found(detail(response))
        if not response.is_success:
            raise self._rejected(method, route, response)
        return response

    def _rejected(self, method: str, route: str, response: httpx.Response) -> Exception:
        """The `rejected` error of an answer the caller refuses (a 4xx it doesn't handle)."""
        return self._errors.rejected(
            f"{self._errors.service} rejected {method} {self._path}{route}: {response.status_code} {detail(response)}"
        )

    def _json(self, response: httpx.Response) -> Json:
        try:
            return response.json()
        except ValueError as e:
            raise self._errors.unavailable(
                f"{self._errors.service} answered something that isn't JSON: {response.url}"
            ) from e

    def _get(self, route: str, params: QueryParams | None = None, not_found: type[Exception] | None = None) -> Json:
        """The decoded answer of a GET; None on 404 when `not_found` isn't given."""
        response = self._request("GET", route, params, not_found=not_found)
        return None if response is None else self._json(response)

    def _object(self, body: Json, what: str) -> Mapping[str, Json]:
        """`body` if it is a JSON object; otherwise the module answered something unexpected (`unavailable`)."""
        if not isinstance(body, Mapping):
            raise self._errors.unavailable(f"{self._errors.service} answered an unexpected {what}: {body!r}")
        return body
