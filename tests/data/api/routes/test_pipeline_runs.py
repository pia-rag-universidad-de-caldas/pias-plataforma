"""The review inbox can read indexed waiting pipeline runs through data."""

from collections.abc import Callable

from fastapi.testclient import TestClient

DataClient = Callable[..., TestClient]


def test_pipeline_runs_by_status_are_paginated_and_keep_the_actor_filter(data_client: DataClient) -> None:
    answer = data_client(
        [{"total": 2}],
        [{"id": "r2", "properties": {"estado": "waiting", "actor": "lab"}}],
    ).get("/pipeline/runs?status=waiting&actor=lab&page=2&per_page=1")

    assert answer.status_code == 200
    assert answer.json() == {
        "page": 2,
        "per_page": 1,
        "total": 2,
        "pages": 2,
        "nodes": [{"label": "PIPE_CORRIDA", "id": "r2", "properties": {"estado": "waiting", "actor": "lab"}}],
    }


def test_pipeline_runs_by_status_require_a_status(data_client: DataClient) -> None:
    assert data_client().get("/pipeline/runs").status_code == 422
