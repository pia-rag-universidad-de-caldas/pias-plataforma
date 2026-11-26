"""What the server refuses before any module sees it (feature 040): a Host it doesn't serve (a web page reaching it
through DNS rebinding), a socket opened from another site and a body too large to read. There is no authentication:
these guards don't replace it if the server is exposed."""

from collections.abc import Collection
from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_413_CONTENT_TOO_LARGE, WS_1008_POLICY_VIOLATION
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from starlette.websockets import WebSocketClose


def _hostname(host: str) -> str | None:
    """The name in a Host header, lowercase and without its port; None if it can't be read."""
    try:
        return urlsplit(f"//{host}").hostname
    except ValueError:
        return None


def same_origin(origin: str | None, host: str) -> bool:
    """Whether a socket comes from the page of this same server. A client that isn't a browser sends no Origin: it
    isn't a page borrowing the user's access, so it passes."""
    if origin is None:
        return True
    try:
        return urlsplit(origin).netloc.lower() == host.lower()
    except ValueError:
        return False


class HostGuard:
    """Answers only to the names in `hosts`: 400 to a request, and a socket is closed before it opens."""

    def __init__(self, app: ASGIApp, hosts: Collection[str]) -> None:
        self._app = app
        self._hosts = frozenset(host.lower() for host in hosts)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self._app(scope, receive, send)
            return
        host = Headers(scope=scope).get("host", "")
        if _hostname(host) in self._hosts:
            await self._app(scope, receive, send)
        elif scope["type"] == "http":
            answer = JSONResponse({"detail": f"this server doesn't answer to the host {host!r}"}, HTTP_400_BAD_REQUEST)
            await answer(scope, receive, send)
        else:
            await WebSocketClose(WS_1008_POLICY_VIOLATION)(scope, receive, send)


class BodyLimit:
    """Refuses a body over `limit` bytes with a 413: by its Content-Length before reading it or, without one, as soon
    as what arrived goes over."""

    def __init__(self, app: ASGIApp, limit: int) -> None:
        self._app = app
        self._limit = limit

    def _message(self) -> str:
        return f"the body goes over the limit of {self._limit} bytes"

    def _declared_too_much(self, scope: Scope) -> bool:
        declared = Headers(scope=scope).get("content-length", "")
        return declared.isdecimal() and int(declared) > self._limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        if self._declared_too_much(scope):
            await JSONResponse({"detail": self._message()}, HTTP_413_CONTENT_TOO_LARGE)(scope, receive, send)
            return
        seen = 0

        async def limited() -> Message:
            nonlocal seen
            message = await receive()
            seen += len(message.get("body", b""))
            if seen > self._limit:  # the error handlers of the module that was reading answer it
                raise HTTPException(HTTP_413_CONTENT_TOO_LARGE, self._message())
            return message

        await self._app(scope, limited, send)
