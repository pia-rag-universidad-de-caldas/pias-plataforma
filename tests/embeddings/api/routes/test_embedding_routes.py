"""The embeddings API on TestClient: data is a dict behind an httpx.MockTransport, the models a fake."""

import time
from collections.abc import Iterator
from dataclasses import dataclass

import httpx
import pytest
from fakes import FakeData, FakeEmbedder, chunked_document
from fastapi.testclient import TestClient

from common.http import Json
from embeddings.adapters import HttpSession
from embeddings.api import ApiSettings, create_app
from embeddings.api.work_queue import WorkQueue
from embeddings.config import DEFAULT_MODEL, MODELS
from embeddings.domain import fingerprint_key, limit_key, vector_property

E5 = "intfloat/multilingual-e5-base"

A, B = "a" * 64, "b" * 64


@dataclass(frozen=True)
class FakeSettings(ApiSettings):
    data: FakeData | None = None

    def session(self) -> HttpSession:
        assert self.data is not None
        return HttpSession(self.self_url, self.data_path, transport=httpx.MockTransport(self.data.handle))


@pytest.fixture
def embedder() -> FakeEmbedder:
    return FakeEmbedder()


def app_client(data: FakeData, embedder: FakeEmbedder) -> TestClient:
    return TestClient(create_app(FakeSettings("http://server", data=data), embedder))


@pytest.fixture
def client(fake_data: FakeData, embedder: FakeEmbedder) -> Iterator[TestClient]:
    with app_client(fake_data, embedder) as test_client:
        yield test_client


def wait(client: TestClient, path: str) -> Json:
    for _ in range(300):
        found = client.get(path).json()
        if found["status"] in ("finished", "failed"):
            return found
        time.sleep(0.01)
    raise AssertionError(f"{path} didn't end")


# runs


@pytest.mark.integration
def test_scenario_a_run_embeds_the_chunked_ones_and_says_which(client: TestClient, fake_data: FakeData) -> None:
    chunked_document(fake_data, A, [["uno", "dos"]])
    started = client.post("/runs", json={"sha256s": [A, B]})
    assert started.status_code == 202
    run = wait(client, f"/runs/{started.json()['id']}")
    assert (run["status"], run["embedded"], run["progress"]["missing"]) == ("finished", [A], 1)
    assert run["config"]["model"] == DEFAULT_MODEL and run["failures"][0]["sha256"] == B
    assert ("CORRIDA_EMBEDDINGS", run["id"]) in fake_data.nodes  # its record outlives the server
    again = wait(client, f"/runs/{client.post('/runs', json={'sha256s': [A]}).json()['id']}")
    assert (again["progress"]["unchanged"], again["embedded"]) == (1, [A])


def test_simulate_answers_200_and_writes_nothing(client: TestClient, fake_data: FakeData) -> None:
    chunked_document(fake_data, A, [["uno"]])
    answer = client.post("/runs", json={"sha256s": [A], "simulate": True})
    assert answer.status_code == 200 and answer.json()["progress"]["embedded"] == 1
    assert fake_data.batches == [] and fake_data.indexes == {}


@pytest.mark.parametrize("body", [{"sha256s": []}, {"sha256s": ["nope"]}, {"sha256s": [A], "limit": 3}])
def test_an_invalid_body_is_422(client: TestClient, body: Json) -> None:
    assert client.post("/runs", json=body).status_code == 422


def test_a_full_line_is_409(fake_data: FakeData, embedder: FakeEmbedder) -> None:
    app = create_app(FakeSettings("http://server", data=fake_data), embedder)
    app.state.queue = WorkQueue(limit=0)
    with TestClient(app) as client:
        assert client.post("/runs", json={"sha256s": [A]}).status_code == 409


def test_without_torch_a_run_is_503(client: TestClient, embedder: FakeEmbedder) -> None:
    embedder.installed = False
    answer = client.post("/runs", json={"sha256s": [A]})
    assert answer.status_code == 503 and "--extra embed" in answer.json()["detail"]


def test_a_run_keeps_the_configuration_it_was_queued_with(client: TestClient, fake_data: FakeData) -> None:
    chunked_document(fake_data, A, [["uno"]])
    client.put("/config", json={"model": DEFAULT_MODEL, "max_tokens": 200})
    run = wait(client, f"/runs/{client.post('/runs', json={'sha256s': [A]}).json()['id']}")
    client.delete("/config")
    assert run["config"]["max_tokens"] == 200
    assert fake_data.nodes[("JSON", A)][limit_key(DEFAULT_MODEL)] == 200


def test_an_unknown_run_is_404(client: TestClient) -> None:
    assert client.get("/runs/nope").status_code == 404


def test_a_run_of_a_past_session_is_read_from_data(fake_data: FakeData, embedder: FakeEmbedder) -> None:
    chunked_document(fake_data, A, [["uno"]])
    with app_client(fake_data, embedder) as first:
        id = wait(first, f"/runs/{first.post('/runs', json={'sha256s': [A]}).json()['id']}")["id"]
    with app_client(fake_data, embedder) as restarted:
        assert restarted.get(f"/runs/{id}").json()["status"] == "finished"
        assert [r["id"] for r in restarted.get("/runs").json()] == [id]


# experiments


@pytest.mark.integration
def test_scenario_an_experiment_embeds_its_chunks_and_apply_makes_it_active(
    client: TestClient, fake_data: FakeData
) -> None:
    chunked_document(fake_data, A, [["uno"]], experiment="c1")
    body = {"name": "minilm", "description": "", "chunking_experiment": "c1", "model": DEFAULT_MODEL, "max_tokens": 64}
    started = client.post("/experiments", json=body)
    assert started.status_code == 202
    found = wait(client, f"/experiments/{started.json()['id']}")
    assert (found["status"], found["embedded"], found["chunking_experiment"]) == ("finished", [A], "c1")
    assert ("EXP_USA", "EXP_EMBEDDINGS", found["id"], "EXPERIMENTO", "c1") in fake_data.links
    applied = client.post(f"/experiments/{found['id']}/apply").json()
    assert (applied["max_tokens"], applied["origin"], applied["experiment"]) == (64, "experimento", found["id"])
    embed = ("EXP_EMBED", f"{found['id']}:c1:{A}:0")
    assert vector_property(DEFAULT_MODEL) in fake_data.nodes[embed]
    assert client.delete(f"/experiments/{found['id']}").status_code == 204
    assert embed not in fake_data.nodes and ("EXP_CHUNK", f"c1:{A}:0") in fake_data.nodes
    assert client.get(f"/experiments/{found['id']}").status_code == 404


def test_an_experiment_over_an_unknown_chunking_experiment_is_404(client: TestClient) -> None:
    assert client.post("/experiments", json={"chunking_experiment": "x", "model": DEFAULT_MODEL}).status_code == 404


def test_an_experiment_over_an_unfinished_one_is_409(client: TestClient, fake_data: FakeData) -> None:
    fake_data.nodes[("EXPERIMENTO", "c1")] = {"estado": "running"}
    assert client.post("/experiments", json={"chunking_experiment": "c1", "model": DEFAULT_MODEL}).status_code == 409


@pytest.mark.parametrize("body", [{"model": "other/model"}, {"model": DEFAULT_MODEL, "max_tokens": 100_000}])
def test_an_experiment_with_a_model_or_limit_that_does_not_fit_is_422(client: TestClient, body: Json) -> None:
    assert client.post("/experiments", json={"chunking_experiment": "c1", **body}).status_code == 422


# configuration, models and vectors


def test_without_a_configuration_it_is_the_default(client: TestClient) -> None:
    found = client.get("/config").json()
    assert (found["model"], found["max_tokens"], found["origin"]) == (DEFAULT_MODEL, 128, "defecto")


def test_put_with_an_unknown_model_is_422(client: TestClient) -> None:
    assert client.put("/config", json={"model": "other/model"}).status_code == 422


def test_patch_changes_only_what_comes_and_delete_goes_back(client: TestClient) -> None:
    client.put("/config", json={"model": DEFAULT_MODEL, "max_tokens": 256})
    assert client.patch("/config", json={"max_tokens": 300}).json()["max_tokens"] == 300
    assert client.delete("/config").json()["max_tokens"] == 128


def test_the_models_say_their_limits_and_the_default(client: TestClient) -> None:
    found = client.get("/models").json()
    assert [m["name"] for m in found] == list(MODELS)
    spec = MODELS[DEFAULT_MODEL]
    assert found[0] == {
        "name": DEFAULT_MODEL,
        "dimensions": spec.dimensions,
        "default_tokens": spec.default_tokens,
        "max_tokens": spec.max_tokens,
        "default": True,
        "documents": None,  # not asked for: data isn't read
    }


def test_the_models_count_their_documents_when_asked(client: TestClient, fake_data: FakeData) -> None:
    fake_data.nodes[("JSON", A)] = {fingerprint_key(DEFAULT_MODEL): "sha256:a", fingerprint_key(E5): "sha256:b"}
    fake_data.nodes[("JSON", B)] = {fingerprint_key(DEFAULT_MODEL): "sha256:c"}
    found = {m["name"]: m["documents"] for m in client.get("/models?documents=true").json()}
    assert found == {DEFAULT_MODEL: 2, E5: 1, "BAAI/bge-m3": 0}


@pytest.mark.integration
def test_scenario_another_model_is_embedded_next_to_the_active_one_and_the_old_one_dropped(
    client: TestClient, fake_data: FakeData
) -> None:
    """Feature 055: a model change without cutting the chat."""
    [chunk] = chunked_document(fake_data, A, [["uno"]])
    wait(client, f"/runs/{client.post('/runs', json={'sha256s': [A]}).json()['id']}")
    run = wait(client, f"/runs/{client.post('/runs', json={'sha256s': [A], 'model': E5}).json()['id']}")
    assert (run["config"]["model"], run["embedded"]) == (E5, [A])
    properties = fake_data.nodes[("FRAGMENTOS", chunk)]
    assert vector_property(DEFAULT_MODEL) in properties and vector_property(E5) in properties  # side by side
    assert client.get("/config").json()["model"] == DEFAULT_MODEL  # the chat still uses the active one
    old = f"/models/{DEFAULT_MODEL}/vectors"
    assert client.delete(old).status_code == 409  # the active one's vectors stay
    client.put("/config", json={"model": E5})
    dropped = client.delete(old).json()
    assert (dropped["index_dropped"], dropped["documents"]) == (True, 1)
    assert vector_property(DEFAULT_MODEL) not in fake_data.nodes[("FRAGMENTOS", chunk)]
    assert fingerprint_key(DEFAULT_MODEL) not in fake_data.nodes[("JSON", A)]
    assert vector_property(E5) in fake_data.nodes[("FRAGMENTOS", chunk)]


def test_dropping_the_vectors_of_a_model_that_is_not_served_is_422(client: TestClient) -> None:
    assert client.delete("/models/other/model/vectors").status_code == 422


def test_a_run_with_a_model_that_is_not_served_is_422(client: TestClient) -> None:
    assert client.post("/runs", json={"sha256s": [A], "model": "other/model"}).status_code == 422


INDEX = "vec_fragmentos_paraphrase_multilingual_minilm_l12_v2_384"
EXPERIMENT_INDEX = "vec_exp_embed_paraphrase_multilingual_minilm_l12_v2_384"


def test_vectors_embed_the_texts_with_the_active_model_and_name_its_indexes(
    client: TestClient, embedder: FakeEmbedder
) -> None:
    client.put("/config", json={"model": DEFAULT_MODEL, "max_tokens": 256})
    answer = client.post("/vectors", json={"texts": ["qué temas", "uno"]})
    assert answer.status_code == 200
    assert answer.json() == {
        "model": DEFAULT_MODEL,
        "max_tokens": 256,
        "dimensions": MODELS[DEFAULT_MODEL].dimensions,
        "index": INDEX,
        "experiment_index": EXPERIMENT_INDEX,
        "vectors": [[2.0, 1.0], [1.0, 1.0]],
    }
    assert embedder.calls[-1] == (DEFAULT_MODEL, ["qué temas", "uno"], 256)


def test_vectors_of_a_model_with_a_query_prefix_read_it(client: TestClient, embedder: FakeEmbedder) -> None:
    found = client.post("/vectors", json={"texts": ["qué temas"], "model": E5}).json()
    assert (found["dimensions"], found["index"]) == (768, "vec_fragmentos_multilingual_e5_base_768")
    assert embedder.calls[-1] == (E5, ["query: qué temas"], 512)


def test_vectors_with_a_model_take_its_default_limit(client: TestClient, embedder: FakeEmbedder) -> None:
    client.put("/config", json={"model": DEFAULT_MODEL, "max_tokens": 256})
    found = client.post("/vectors", json={"texts": ["a"], "model": DEFAULT_MODEL, "max_tokens": 64}).json()
    assert found["max_tokens"] == 64 and embedder.calls[-1][2] == 64


@pytest.mark.parametrize(
    "body",
    [{"texts": []}, {"texts": [""]}, {"texts": ["a"], "k": 3}, {"texts": ["a"], "model": "other/model"}],
    ids=["no texts", "an empty text", "an unknown key", "a model that isn't served"],
)
def test_vectors_refuse_what_they_can_not_embed(client: TestClient, body: dict[str, object]) -> None:
    assert client.post("/vectors", json=body).status_code == 422


def test_too_many_texts_are_422(client: TestClient) -> None:
    assert client.post("/vectors", json={"texts": ["a"] * 65}).status_code == 422


def test_the_search_left_embeddings(client: TestClient) -> None:
    assert client.post("/search", json={"question": "a"}).status_code == 404


def test_vectors_without_the_model_are_503(client: TestClient, embedder: FakeEmbedder) -> None:
    embedder.down = True
    assert client.post("/vectors", json={"texts": ["a"]}).status_code == 503
