"""GET /targets (feature 060) on TestClient, with embeddings and data as FakeModules (the chunking experiments are
read from data: consultas never calls chunking)."""

import json
from collections.abc import Iterator

import pytest
from consultas_fakes import FakeModules
from fastapi.testclient import TestClient

from consultas.api import ApiSettings, create_app


@pytest.fixture
def fake() -> FakeModules:
    return FakeModules()


@pytest.fixture
def client(fake: FakeModules) -> Iterator[TestClient]:
    with TestClient(create_app(ApiSettings("http://server"), fake.modules())) as test_client:
        yield test_client


def experiment(id: str, status: str = "finished") -> dict[str, object]:
    return {
        "id": id,
        "kind": "experiment",
        "status": status,
        "name": f"exp {id}",
        "config": {"model": "m2", "max_tokens": 256},
        "chunking_experiment": "c1",
        "embedded": ["a" * 64, "b" * 64],
    }


def test_targets_answer_the_contract(client: TestClient, fake: FakeModules) -> None:
    fake.coverage = {"embedding_m_2": (8, 10)}
    fake.embedding_runs = [experiment("x1"), experiment("x2", status="running")]
    fake.nodes[("EXPERIMENTO", "c1")] = {
        "nombre": "hybrid 254",
        "estado": "finished",
        "chunking": json.dumps({"chunker": "hybrid", "tokenizer": "m2", "max_tokens": 254, "merge_peers": True}),
    }
    found = client.get("/targets").json()
    assert found == {
        "official": [{"model": "m", "dimensions": 2, "active": True, "documents_done": 8, "documents_total": 10}],
        "experiments": [
            {
                "embeddings_experiment": "x1",
                "name": "exp x1",
                "model": "m2",
                "dimensions": 3,
                "chunking_experiment": "c1",
                "chunking_name": "hybrid 254",
                "chunking": {"chunker": "hybrid", "tokenizer": "m2", "max_tokens": 254},
                "documents": 2,
            }
        ],
    }


def test_a_model_with_official_vectors_is_a_target_though_not_active(client: TestClient, fake: FakeModules) -> None:
    fake.coverage = {"embedding_m2_3": (1, 10)}
    found = client.get("/targets").json()["official"]
    assert [(t["model"], t["active"]) for t in found] == [("m", True), ("m2", False)]


@pytest.mark.parametrize("service", ["embeddings", "data"])
def test_a_module_down_is_503_saying_which(client: TestClient, fake: FakeModules, service: str) -> None:
    fake.embedding_runs = [experiment("x1")]
    fake.down = {service}
    found = client.get("/targets")
    assert found.status_code == 503 and found.json()["detail"].startswith(f"{service} is not answering")
