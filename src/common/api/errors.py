"""The errors of a module's API as JSON (feature 033): every HTTPException and every exception the module maps to a
code answer `{key: message}`. `key` is the module's published one: "detail" (data, chunking, pipeline) or "detalle"
(ingesta)."""

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException  # Starlette's: also the 404 of a URL that doesn't exist


@dataclass(frozen=True)
class Error:
    detail: str


def error_handlers(app: FastAPI, codes: Mapping[type[Exception], int], key: str = "detail") -> None:
    """HTTP errors (a 404 from a route or from a URL that doesn't exist...) and each exception of `codes` with its
    status code, all with the `{key: message}` body. Starlette picks the handler of the closest class (MRO), so a
    subclass can have its own code and its base another."""

    async def http_error(_: Request, error: Exception) -> JSONResponse:
        assert isinstance(error, HTTPException)
        return JSONResponse(status_code=error.status_code, content={key: error.detail}, headers=error.headers)

    app.add_exception_handler(HTTPException, http_error)
    for kind, code in codes.items():
        app.add_exception_handler(kind, _answer(code, key))


def _answer(code: int, key: str) -> Callable[[Request, Exception], Awaitable[JSONResponse]]:
    async def answer(_: Request, error: Exception) -> JSONResponse:
        return JSONResponse(status_code=code, content={key: str(error)})

    return answer
