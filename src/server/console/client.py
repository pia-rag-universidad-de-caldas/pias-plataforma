"""The console's only way to the modules: HTTP against the single server."""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Self

import httpx

from .bodies import JsonValue, dump
from .catalog import Module, Operation, operations
from .expansions import expand
from .requests import PreparedRequest

HEALTH_TIMEOUT = 2.0
REQUEST_TIMEOUT = 120.0  # an answer can take long (a big /stats, a simulated ingestion over the whole corpus)
MAX_SHOWN = 500_000  # characters of an answer shown; the rest is cut


class ServerError(Exception):
    """The server didn't answer or its openapi.json is not usable."""


@dataclass(frozen=True)
class Reply:
    status: int
    content_type: str
    text: str  # what to show: indented JSON, the text, or the type and size of a binary answer
    id: str | None = None  # the top-level "id" of a JSON answer, offered in the next `id` field
    data: JsonValue = None  # the decoded JSON answer (tables, progress)

    @property
    def ok(self) -> bool:
        return self.status < 400


def _id(body: object) -> str | None:
    """The id of what was just created or read: {"id"} or one level down ({"run": {"id"}})."""
    if not isinstance(body, dict):
        return None
    found = body.get("id")
    if isinstance(found, str | int):
        return str(found)
    for value in body.values():
        if isinstance(value, dict) and isinstance(value.get("id"), str | int):
            return str(value["id"])
    return None


def reply(response: httpx.Response) -> Reply:
    content_type = response.headers.get("content-type", "").split(";")[0]
    if not response.content:
        return Reply(response.status_code, content_type, "(respuesta vacía)")
    if content_type == "application/json":
        try:
            body = response.json()
        except json.JSONDecodeError:
            pass
        else:
            return Reply(response.status_code, content_type, dump(body)[:MAX_SHOWN], _id(body), body)
    if content_type.startswith("text/"):
        return Reply(response.status_code, content_type, response.text[:MAX_SHOWN])
    return Reply(response.status_code, content_type, f"({len(response.content):,} bytes de {content_type or '?'})")


class ApiClient:
    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    @classmethod
    def to(cls, url: str) -> Self:
        return cls(httpx.Client(base_url=url, timeout=REQUEST_TIMEOUT))

    def close(self) -> None:
        self._client.close()

    def health(self) -> Reply | None:
        """GET /health of the server, or None if it doesn't answer."""
        try:
            return reply(self._client.get("/health", timeout=HEALTH_TIMEOUT))
        except httpx.HTTPError:
            return None

    def operations(self, module: Module) -> tuple[Operation, ...]:
        """The module's operations, read from its openapi.json."""
        try:
            response = self._client.get(f"{module.prefix}/openapi.json", timeout=HEALTH_TIMEOUT * 5)
            response.raise_for_status()
            spec: object = response.json()
        except (httpx.HTTPError, json.JSONDecodeError) as error:
            raise ServerError(f"no se pudo leer {module.prefix}/openapi.json: {error}") from error
        if not isinstance(spec, dict):
            raise ServerError(f"{module.prefix}/openapi.json no es un documento OpenAPI")
        return tuple(expand(operation) for operation in operations(spec, module))

    def get_json(self, path: str, params: Mapping[str, str] | Sequence[tuple[str, str]]) -> JsonValue:
        """A GET's JSON for the console's own use (suggestions, home, progress); None if anything fails."""
        try:
            query = tuple(params.items()) if isinstance(params, Mapping) else tuple(params)
            response = self._client.get(path, params=query, timeout=HEALTH_TIMEOUT * 5)
            if response.status_code >= 400:
                return None
            body: JsonValue = response.json()
        except (httpx.HTTPError, json.JSONDecodeError):
            return None
        return body

    def post_json(self, path: str, body: JsonValue) -> JsonValue:
        """A POST that only reads (POST /data/documents/select, feature 062) for the console's own use; None if
        anything fails."""
        try:
            response = self._client.post(path, json=body, timeout=HEALTH_TIMEOUT * 5)
            if response.status_code >= 400:
                return None
            found: JsonValue = response.json()
        except (httpx.HTTPError, json.JSONDecodeError):
            return None
        return found

    def send(self, request: PreparedRequest) -> Reply:
        """The answer, whatever its status; ServerError only if the server didn't answer."""
        try:
            response = self._client.request(
                request.method,
                request.path,
                params=request.params,
                json=request.body if request.has_body else None,
            )
        except httpx.HTTPError as error:
            raise ServerError(f"{request.method} {request.path}: el servidor no respondió ({error})") from error
        return reply(response)
