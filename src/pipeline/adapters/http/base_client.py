"""The base of the pipeline's HTTP clients (the pattern of chunking's, feature 026; not imported: modules don't import
each other). Sending, the status → error rules and reading JSON live only here; each client adds its routes."""

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

import httpx

from pipeline.models import RejectedError, UnavailableError

type QueryParams = tuple[tuple[str, str | int], ...]
type Json = Any  # a decoded JSON answer of another module (checked where it is read)

NOT_FOUND = 404
CONFLICT = 409


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
    """`path` is the module's prefix on the server (/ingesta, /data, /chunking); routes are relative to it. Network
    errors, timeouts, 5xx and answers that aren't JSON are UnavailableError; a 4xx the caller doesn't handle is
    RejectedError."""

    def __init__(self, client: httpx.Client, path: str, service: str) -> None:
        self._client = client
        self._path = path.rstrip("/")
        self._service = service

    def _send(self, method: str, route: str, params: QueryParams | None = None, body: object = None) -> httpx.Response:
        url = f"{self._path}{route}"
        try:
            response = self._client.request(method, url, params=params, json=body)
        except httpx.TimeoutException as e:
            raise UnavailableError(f"{method} {url}: no answer within {self._client.timeout.read}s") from e
        except httpx.HTTPError as e:
            raise UnavailableError(f"{method} {url}: {e}") from e
        if response.is_server_error:
            raise UnavailableError(f"{method} {url}: {response.status_code} {detail(response)}")
        return response

    def _rejected(self, method: str, route: str, response: httpx.Response) -> RejectedError:
        return RejectedError(
            f"{self._service} rejected {method} {self._path}{route}: {response.status_code} {detail(response)}"
        )

    def _request(
        self, method: str, route: str, params: QueryParams | None = None, body: object = None
    ) -> httpx.Response | None:
        """A successful answer; None on 404; another 4xx is RejectedError."""
        response = self._send(method, route, params, body)
        if response.status_code == NOT_FOUND:
            return None
        if not response.is_success:
            raise self._rejected(method, route, response)
        return response

    def _json(self, response: httpx.Response) -> Json:
        try:
            return response.json()
        except ValueError as e:
            raise UnavailableError(f"{self._service} answered something that isn't JSON: {response.url}") from e

    def _get(self, route: str, params: QueryParams | None = None) -> Json:
        """The decoded answer of a GET; None on 404."""
        response = self._request("GET", route, params)
        return None if response is None else self._json(response)

    def _object(self, body: Json, what: str) -> Mapping[str, Json]:
        if not isinstance(body, Mapping):
            raise UnavailableError(f"{self._service} answered an unexpected {what}: {body!r}")
        return body
