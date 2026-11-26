"""The embeddings API on TestClient: data is a dict behind an httpx.MockTransport, the models a fake."""

import threading
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
        if found["status"] in ("finished", "failed", "cancelled"):
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


def test_a_run_without_sha256s_takes_what_is_missing(client: TestClient, fake_data: FakeData) -> None:
    chunked_document(fake_data, A, [["uno"]])
    fake_data.nodes[("JSON", A)]["huella_chunking"] = "c1"
    chunked_document(fake_data, B, [["dos"]], state="error")  # not chunked: never missing
    run = wait(client, f"/runs/{client.post('/runs', json={}).json()['id']}")
    assert (run["status"], run["sha256s"], run["embedded"]) == ("finished", [A], [A])
    again = client.post("/runs", json={"simulate": True}).json()  # its mark says it's done
    assert again["sha256s"] == [] and again["progress"]["total"] == 0


def test_simulate_answers_200_and_writes_nothing(client: TestClient, fake_data: FakeData) -> None:
    chunked_document(fake_data, A, [["uno"]])
    answer = client.post("/runs", json={"sha256s": [A], "simulate": True})
    assert answer.status_code == 200 and answer.json()["progress"]["embedded"] == 1
    assert fake_data.batches == [] and fake_data.indexes == {}


@pytest.mark.parametrize(
    "body", [{"sha256s": [A], "page": 1}, {"sha256s": ["nope"]}, {"sha256s": [A], "limit": 3}, {"per_page": 0}]
)
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


class GatedEmbedder(FakeEmbedder):
    """Embeds only when the test opens its gate (feature 056: a run is cancelled while it embeds)."""

    def __init__(self) -> None:
        super().__init__()
        self.embedding, self.gate = threading.Event(), threading.Event()

    def embed(self, model: str, texts: list[str], max_tokens: int) -> list[list[float]]:
        self.embedding.set()
        self.gate.wait(5)
        return super().embed(model, texts, max_tokens)


@pytest.mark.integration
def test_cancel_lets_the_running_document_end_and_embeds_no_more(fake_data: FakeData) -> None:
    chunked_document(fake_data, A, [["uno"]])
    chunked_document(fake_data, B, [["dos"]])
    embedder = GatedEmbedder()
    with app_client(fake_data, embedder) as client:
        id = client.post("/runs", json={"sha256s": [A, B]}).json()["id"]
        assert embedder.embedding.wait(5)
        asked = client.post(f"/runs/{id}/cancel")
        assert asked.status_code == 200 and asked.json()["cancel_requested"] is True
        embedder.gate.set()
        run = wait(client, f"/runs/{id}")
        assert (run["status"], run["embedded"]) == ("cancelled", [A])
        assert client.post(f"/runs/{id}/cancel").status_code == 409  # it already ended
        assert client.post("/runs/nope/cancel").status_code == 404


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


def test_an_experiment_a_pipeline_run_links_is_deleted_only_with_force(client: TestClient, fake_data: FakeData) -> None:
    """Feature 055 part b: the pipeline rewrites its whole run, and a missing end would make it fail."""
    chunked_document(fake_data, A, [["uno"]], experiment="c1")
    body = {"chunking_experiment": "c1", "model": DEFAULT_MODEL}
    id = wait(client, f"/experiments/{client.post('/experiments', json=body).json()['id']}")["id"]
    fake_data.nodes[("PIPE_ITERACION", "it1")] = {}
    fake_data.link("PIPE_USA", ("PIPE_ITERACION", "it1"), ("EXP_EMBEDDINGS", id))
    answer = client.delete(f"/experiments/{id}")
    assert answer.status_code == 409 and "it1" in answer.json()["detail"]
    assert ("EXP_EMBEDDINGS", id) in fake_data.nodes
    assert client.delete(f"/experiments/{id}?force=true").status_code == 204
    assert ("EXP_EMBEDDINGS", id) not in fake_data.nodes


def test_an_experiment_over_an_unknown_chunking_experiment_is_404(client: TestClient) -> None:
    assert client.post("/experiments", json={"chunking_experiment": "x", "model": DEFAULT_MODEL}).status_code == 404


def test_an_experiment_over_an_unfinished_one_is_409(client: TestClient, fake_data: FakeData) -> None:
    fake_data.nodes[("EXPERIMENTO", "c1")] = {"estado": "running"}
    assert client.post("/experiments", json={"chunking_experiment": "c1", "model": DEFAULT_MODEL}).status_code == 409


def test_an_experiment_over_a_partial_one_embeds_what_it_chunked(client: TestClient, fake_data: FakeData) -> None:
    chunked_document(fake_data, A, [["uno"]], experiment="c1")
    fake_data.nodes[("EXPERIMENTO", "c1")]["estado"] = "partial"  # feature 059
    started = client.post("/experiments", json={"chunking_experiment": "c1", "model": DEFAULT_MODEL})
    assert started.status_code == 202
    assert wait(client, f"/experiments/{started.json()['id']}")["embedded"] == [A]


@pytest.mark.integration
def test_scenario_several_experiments_over_one_chunking_experiment_coexist_and_are_listed_by_it(
    client: TestClient, fake_data: FakeData
) -> None:
    chunked_document(fake_data, A, [["uno", "dos"]], experiment="c1")
    chunked_document(fake_data, B, [["tres"]], experiment="c2")
    ids = []
    for chunking, model in (("c1", DEFAULT_MODEL), ("c1", E5), ("c1", DEFAULT_MODEL), ("c2", DEFAULT_MODEL)):
        started = client.post("/experiments", json={"chunking_experiment": chunking, "model": model})
        assert started.status_code == 202
        ids.append(wait(client, f"/experiments/{started.json()['id']}")["id"])
    listed = client.get("/experiments", params={"chunking_experiment": "c1"}).json()
    assert sorted(e["id"] for e in listed) == sorted(ids[:3])
    assert len(client.get("/experiments").json()) == 4
    e5 = next(e for e in listed if e["id"] == ids[1])
    assert (e5["model"], e5["dimensions"], e5["max_tokens"]) == (E5, MODELS[E5].dimensions, MODELS[E5].default_tokens)
    assert (e5["documents"], e5["chunks"], e5["status"], e5["chunking_experiment"]) == (1, 2, "finished", "c1")
    assert e5["config"]["model"] == E5  # what was there before stays
    embeds = {id for label, id in fake_data.nodes if label == "EXP_EMBED"}
    assert {f"{id}:c1:{A}:0" for id in ids[:3]} <= embeds  # the same model twice: a vector each
    assert client.delete(f"/experiments/{ids[0]}").status_code == 204
    assert f"{ids[2]}:c1:{A}:0" in {id for label, id in fake_data.nodes if label == "EXP_EMBED"}


def test_an_experiment_says_its_model_and_dimensions(client: TestClient, fake_data: FakeData) -> None:
    chunked_document(fake_data, A, [["uno"]], experiment="c1")
    id = client.post("/experiments", json={"chunking_experiment": "c1", "model": DEFAULT_MODEL}).json()["id"]
    found = wait(client, f"/experiments/{id}")
    assert (found["model"], found["dimensions"]) == (DEFAULT_MODEL, MODELS[DEFAULT_MODEL].dimensions)


def embedded_experiment(client: TestClient) -> str:
    """An experiment over chunking experiment c1 with the default model, once it ended."""
    started = client.post("/experiments", json={"chunking_experiment": "c1", "model": DEFAULT_MODEL})
    found = wait(client, f"/experiments/{started.json()['id']}")
    return str(found["id"])


@pytest.mark.integration
def test_scenario_an_experiment_continues_over_what_its_chunking_experiment_got_afterwards(
    client: TestClient, fake_data: FakeData
) -> None:
    """Feature 062: documents added to the chunking experiment are embedded by resuming, and only them."""
    chunked_document(fake_data, A, [["uno"]], experiment="c1")
    id = embedded_experiment(client)
    assert client.get(f"/experiments/{id}").json()["pending"] == 0
    assert client.post(f"/experiments/{id}/resume").status_code == 409  # nothing missing
    chunked_document(fake_data, B, [["dos", "tres"]], experiment="c1")
    assert client.get(f"/experiments/{id}").json()["pending"] == 1
    resumed = client.post(f"/experiments/{id}/resume")
    assert resumed.status_code == 202 and resumed.json()["pending"] == 1
    found = wait(client, f"/experiments/{id}")
    assert (found["embedded"], found["documents"], found["resumed"], found["pending"]) == ([A, B], 2, 1, 0)
    assert ("EXP_EMBED", f"{id}:c1:{B}:1") in fake_data.nodes


def test_resuming_with_sha256s_takes_only_those_of_what_is_missing(client: TestClient, fake_data: FakeData) -> None:
    chunked_document(fake_data, A, [["uno"]], experiment="c1")
    id = embedded_experiment(client)
    chunked_document(fake_data, B, [["dos"]], experiment="c1")
    assert client.post(f"/experiments/{id}/resume", json={"sha256s": [A]}).status_code == 409  # A has its vectors
    assert client.post(f"/experiments/{id}/resume", json={"sha256s": [B]}).status_code == 202


def test_resuming_an_unknown_experiment_is_404(client: TestClient) -> None:
    assert client.post("/experiments/nope/resume").status_code == 404


def test_a_finished_run_without_anything_left_isnt_resumed(client: TestClient, fake_data: FakeData) -> None:
    chunked_document(fake_data, A, [["uno"]])
    run = wait(client, f"/runs/{client.post('/runs', json={'sha256s': [A]}).json()['id']}")
    assert client.post(f"/runs/{run['id']}/resume").status_code == 409
    assert client.post("/runs/nope/resume").status_code == 404


def test_a_run_with_a_document_left_is_resumed_with_its_list_skipping_what_is_done(
    client: TestClient, fake_data: FakeData
) -> None:
    chunked_document(fake_data, A, [["uno"]])
    chunked_document(fake_data, B, [["dos"]], state="error")  # not chunked yet: skipped
    run = wait(client, f"/runs/{client.post('/runs', json={'sha256s': [A, B]}).json()['id']}")
    assert run["progress"]["skipped"] == 1
    fake_data.nodes[("JSON", B)]["estado_chunking"] = "fragmentado"
    resumed = client.post(f"/runs/{run['id']}/resume")
    assert resumed.status_code == 202 and resumed.json()["id"] == run["id"]
    found = wait(client, f"/runs/{run['id']}")
    assert (found["progress"]["unchanged"], found["progress"]["embedded"], found["resumed"]) == (1, 1, 1)


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
        "vector_property": "embedding_paraphrase_multilingual_minilm_l12_v2_384",
        "passage_budget": 510,  # 512 - 2 special tokens
        "default_passage_budget": 126,
        "official_passage_budget": 126,  # 128 + the course's 48 still fit in its 512 positions
    }


def test_a_passage_prefix_and_the_course_in_front_come_off_the_budgets(client: TestClient) -> None:
    """Feature 062: e5 reads `passage: ` (1 word for the fake) in front of a chunk, and its 512 positions are its
    default too, so an official chunk leaves the course's HEADING_TOKENS."""
    e5 = {m["name"]: m for m in client.get("/models").json()}[E5]
    budgets = (e5["passage_budget"], e5["default_passage_budget"], e5["official_passage_budget"])
    assert budgets == (509, 509, 512 - 48 - 3)


def test_without_the_embed_extra_only_a_prefix_that_cant_be_counted_is_unknown(
    fake_data: FakeData, embedder: FakeEmbedder
) -> None:
    embedder.installed = False
    with app_client(fake_data, embedder) as client:
        found = {m["name"]: m["passage_budget"] for m in client.get("/models").json()}
    assert found == {DEFAULT_MODEL: 510, E5: None, "BAAI/bge-m3": 8190}


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
