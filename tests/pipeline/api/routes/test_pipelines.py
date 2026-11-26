"""POST /pipelines/check (feature 039): the flow editor asks after each change, and nothing is saved."""

from fastapi.testclient import TestClient

from pipeline.api import ApiSettings, create_app


def client() -> TestClient:
    return TestClient(create_app(ApiSettings("http://server.test")))


def test_stages_that_can_run_are_accepted() -> None:
    response = client().post("/pipelines/check", json={"stages": [{"id": "a", "action": "ingesta.chunkable"}]})
    assert response.status_code == 200 and response.json() == {"stages": 1}


def test_stages_that_cannot_run_say_why() -> None:
    body = {"stages": [{"id": "fijar", "action": "chunking.apply"}]}
    response = client().post("/pipelines/check", json=body)
    assert response.status_code == 422 and "fijar" in response.json()["detail"]
