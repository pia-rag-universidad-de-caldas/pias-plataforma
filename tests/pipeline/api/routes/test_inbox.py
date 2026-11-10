"""PUT /actors/{name} (feature 040): a callback_url that can't be used is refused before it is kept."""

import pytest
from fastapi.testclient import TestClient

from pipeline.api import ApiSettings, create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(ApiSettings("http://127.0.0.1:1")))


@pytest.mark.parametrize(
    "url", ["http://169.254.169.254/latest/meta-data", "http://[bad", "file:///etc/passwd", "http://example.com/hook"]
)
def test_a_callback_that_cant_be_used_is_422(client: TestClient, url: str) -> None:
    assert client.put("/actors/lab", json={"callback_url": url}).status_code == 422


def test_a_refused_callback_is_not_kept(client: TestClient) -> None:
    client.put("/actors/lab", json={"callback_url": "http://169.254.169.254/"})
    assert next(a for a in client.get("/actors").json() if a["name"] == "lab")["callback_url"] is None


def test_a_loopback_callback_is_kept(client: TestClient) -> None:
    answer = client.put("/actors/lab", json={"callback_url": "http://127.0.0.1:9000/hook"})
    assert answer.status_code == 200 and answer.json()["callback_url"] == "http://127.0.0.1:9000/hook"


def test_no_callback_is_still_allowed(client: TestClient) -> None:
    assert client.put("/actors/lab", json={}).status_code == 200
