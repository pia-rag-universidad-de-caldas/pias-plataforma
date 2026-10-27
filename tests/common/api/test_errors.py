"""error_handlers (feature 033): every error of a module's API with its code and the module's key."""

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from common.api import error_handlers


class Down(Exception):
    pass


class Gone(Down):
    pass


def app(key: str) -> TestClient:
    api = FastAPI()
    error_handlers(api, {Down: 503, Gone: 410}, key=key)

    @api.get("/down")
    def down() -> None:
        raise Down("Neo4j is down")

    @api.get("/gone")
    def gone() -> None:
        raise Gone("it was deleted")

    @api.get("/missing")
    def missing() -> None:
        raise HTTPException(404, "no such thing", headers={"X-Why": "test"})

    return TestClient(api)


def test_each_exception_with_its_code_and_the_closest_class_wins() -> None:
    client = app("detail")
    down, gone = client.get("/down"), client.get("/gone")
    assert (down.status_code, down.json()) == (503, {"detail": "Neo4j is down"})
    assert (gone.status_code, gone.json()) == (410, {"detail": "it was deleted"})


def test_http_errors_keep_their_headers_and_use_the_module_key_also_for_unknown_urls() -> None:
    client = app("detalle")
    missing = client.get("/missing")
    assert (missing.status_code, missing.json(), missing.headers["x-why"]) == (
        404,
        {"detalle": "no such thing"},
        "test",
    )
    assert client.get("/nope").json() == {"detalle": "Not Found"}  # Starlette's 404, not only FastAPI's
