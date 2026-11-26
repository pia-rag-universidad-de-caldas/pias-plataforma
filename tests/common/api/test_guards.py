"""The server's guards (feature 040): which Host it answers to and how large a body it reads."""

from collections.abc import Iterator

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from common.api import BodyLimit, HostGuard, error_handlers, same_origin

LIMIT = 10


def guarded() -> TestClient:
    app = FastAPI()
    error_handlers(app, {})

    @app.post("/echo")
    async def echo(request: Request) -> int:
        return len(await request.body())

    @app.post("/typed")
    def typed(body: dict[str, str]) -> int:
        return len(body)

    @app.get("/ping")
    def ping() -> str:
        return "pong"

    app.add_middleware(BodyLimit, limit=LIMIT)
    app.add_middleware(HostGuard, hosts=frozenset({"localhost", "::1"}))
    return TestClient(app, base_url="http://localhost:8000", raise_server_exceptions=False)


def test_a_known_host_is_answered_whatever_its_port() -> None:
    assert guarded().get("/ping", headers={"Host": "localhost:1234"}).status_code == 200


def test_an_ipv6_host_is_understood() -> None:
    assert guarded().get("/ping", headers={"Host": "[::1]:8000"}).status_code == 200


def test_an_unknown_host_is_400_with_the_json_error() -> None:
    answer = guarded().get("/ping", headers={"Host": "evil.example"})
    assert answer.status_code == 400 and "evil.example" in answer.json()["detail"]


def test_a_host_is_compared_without_case() -> None:
    assert guarded().get("/ping", headers={"Host": "LOCALHOST"}).status_code == 200


def test_a_body_within_the_limit_passes() -> None:
    assert guarded().post("/echo", content=b"x" * LIMIT).json() == LIMIT


def test_a_declared_length_over_the_limit_is_413() -> None:
    assert guarded().post("/echo", content=b"x" * (LIMIT + 1)).status_code == 413


def test_a_chunked_body_over_the_limit_is_413() -> None:
    def chunks() -> Iterator[bytes]:
        yield b"x" * LIMIT
        yield b"x"

    assert guarded().post("/echo", content=chunks()).status_code == 413


def test_a_chunked_body_over_the_limit_is_413_also_on_a_typed_route() -> None:
    def chunks() -> Iterator[bytes]:
        yield b'{"a": "'
        yield b"x" * LIMIT
        yield b'"}'

    answer = guarded().post("/typed", content=chunks(), headers={"Content-Type": "application/json"})
    assert answer.status_code == 413


def test_a_chunked_body_within_the_limit_passes() -> None:
    def chunks() -> Iterator[bytes]:
        yield b"xx"
        yield b"xx"

    assert guarded().post("/echo", content=chunks()).json() == 4


def test_no_origin_counts_as_same_origin() -> None:
    assert same_origin(None, "localhost:8000")


def test_the_same_host_and_port_is_same_origin() -> None:
    assert same_origin("http://LOCALHOST:8000", "localhost:8000")


def test_another_port_is_not_same_origin() -> None:
    assert not same_origin("http://localhost:3000", "localhost:8000")


def test_another_site_is_not_same_origin() -> None:
    assert not same_origin("http://evil.example", "localhost:8000")


def test_the_null_origin_is_not_same_origin() -> None:
    assert not same_origin("null", "localhost:8000")
