"""The routes of chunking (features 043 and 045) over fake stores: experiments, the active configuration and the runs.
No data, no docling-core: what would run in line is caught before it starts."""

from collections.abc import Iterator
from dataclasses import replace
from importlib import import_module
from typing import Any

import pytest
from fastapi.testclient import TestClient

from chunking.api import ApiSettings, create_app
from chunking.api.dependencies import _config, _probe, _run_store, _store
from chunking.domain import ExperimentGraph, Parameters
from chunking.models import (
    ActiveConfig,
    Chunk,
    Chunker,
    ChunkingParameters,
    ChunkingRun,
    ConfigOrigin,
    DocumentUse,
    ExperimentProgress,
    ExperimentRecord,
    ExperimentRequest,
    ExperimentStatus,
    GraphBatch,
    ParsedDocument,
    RequestedChunking,
    RunStatus,
)

A, B = "a" * 64, "b" * 64
PARAMETERS = Parameters.resolve(RequestedChunking(), "2")


def record(id: str, status: ExperimentStatus = ExperimentStatus.FINISHED) -> ExperimentRecord:
    stored = ExperimentGraph.experiment(id, ExperimentRequest(id, "", PARAMETERS, [A, B]), 0, "").nodes[0].properties
    return ExperimentRecord(
        id,
        id,
        "",
        status,
        "2026",
        None,
        ExperimentProgress(),
        str(stored["documentos"]),
        str(stored["chunking"]),
        None,
        None,
        parameters=PARAMETERS,
    )


class Store:
    """ExperimentStore and ConfigStore and RunStore, all in memory."""

    def __init__(self) -> None:
        self.records = {
            "done": record("done"),
            "busy": record("busy", ExperimentStatus.RUNNING),
            "half": record("half", ExperimentStatus.PARTIAL),
        }
        self.saved: list[GraphBatch] = []
        self.config: ActiveConfig | None = None
        self.stored_runs: dict[str, ChunkingRun] = {}
        self.missing_asked: tuple[str, int | None, int | None] | None = None

    def document(self, sha256: str) -> ParsedDocument | None:
        return ParsedDocument(sha256, "parseado", "p", "stored") if sha256 == A else None

    def save(self, batch: GraphBatch) -> None:
        self.saved.append(batch)

    def experiment(self, id: str) -> ExperimentRecord | None:
        return self.records.get(id)

    def experiments(self) -> list[ExperimentRecord]:
        return list(self.records.values())

    def documents(self, experiment_id: str) -> list[str]:
        return [A]

    def uses(self, experiment_id: str) -> list[DocumentUse]:
        return [DocumentUse(A, False, 0, [])]

    def missing(self, fingerprint: str, page: int | None, per_page: int | None) -> list[str]:
        self.missing_asked = (fingerprint, page, per_page)
        return [A, B]

    def delete(self, id: str) -> bool:
        return self.records.pop(id, None) is not None

    def chunked_with(self) -> list[ChunkingParameters | None]:
        return [PARAMETERS, None, replace(PARAMETERS, max_tokens=64)]

    def stored(self) -> ActiveConfig | None:
        return self.config

    def put(self, config: ActiveConfig) -> None:
        self.config = config

    def clear(self) -> bool:
        found, self.config = self.config is not None, None
        return found

    def run(self, id: str) -> ChunkingRun | None:
        return self.stored_runs.get(id)

    def runs(self) -> list[ChunkingRun]:
        return list(self.stored_runs.values())


class Ready(Chunker):
    def available(self) -> bool:
        return True

    def version(self) -> str | None:
        return "2"

    def chunk(self, content: str, parameters: ChunkingParameters) -> list[Chunk]:
        return [Chunk(0, "t", "t", [], [1], 1)]


class Answers:
    def responds(self, path: str) -> bool:
        return True


@pytest.fixture
def store() -> Store:
    return Store()


@pytest.fixture
def launched(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """What would have been put in line, instead of running it."""
    found: list[str] = []
    # routes/__init__ names the routers like the modules: the modules themselves
    experiments, runs = (import_module(f"chunking.api.routes.{name}") for name in ("experiments", "runs"))
    monkeypatch.setattr(experiments, "launch", lambda *args: found.append(args[2]))
    monkeypatch.setattr(runs, "launch", lambda *args: found.append(args[2].id))
    return found


@pytest.fixture
def client(store: Store) -> Iterator[TestClient]:
    app = create_app(ApiSettings("http://127.0.0.1:1"), Ready())

    def stores() -> Iterator[Store]:
        yield store

    for dependency in (_store, _config, _run_store):
        app.dependency_overrides[dependency] = stores
    app.dependency_overrides[_probe] = Answers
    with TestClient(app) as test_client:
        yield test_client


def test_health_only_asks_data(client: TestClient) -> None:
    body: dict[str, Any] = client.get("/health").json()
    assert (body["status"], body["data"], body["docling_core"]) == ("ok", "ok", "installed")
    assert "ingesta" not in body


@pytest.mark.parametrize(
    "body",
    [
        {"name": "x"},
        {"name": "x", "sha256s": [A], "from_experiment": "done"},
        {"name": "x", "sha256s": [A], "chunking": {"chunker": "page", "max_tokens": 64}},
        {"name": "x", "sha256s": [A], "plan": {}},
    ],
)
def test_an_experiment_that_cant_be_is_422(client: TestClient, body: dict[str, object]) -> None:
    assert client.post("/experiments", json=body).status_code == 422


def test_an_experiment_without_parsed_documents_is_409(client: TestClient) -> None:
    answer = client.post("/experiments", json={"name": "x", "sha256s": [B]})
    assert answer.status_code == 409 and "/parsing/runs" in answer.json()["detail"]


def test_simulating_an_experiment_says_what_enters(client: TestClient, store: Store, launched: list[str]) -> None:
    answer = client.post("/experiments", json={"name": "x", "sha256s": [A, B], "simulate": True})
    assert answer.status_code == 200
    assert (answer.json()["documents"], answer.json()["unparsed"]) == ([A], [B])
    assert answer.json()["chunking"]["max_tokens"] == 126
    assert store.saved == [] and launched == []


def test_an_experiment_is_stored_and_put_in_line(client: TestClient, store: Store, launched: list[str]) -> None:
    answer = client.post("/experiments", json={"name": "x", "sha256s": [A], "chunking": {"chunker": "hierarchical"}})
    assert answer.status_code == 202 and launched == [answer.json()["id"]]
    assert store.saved[0].nodes[0].properties["nombre"] == "x"


def test_an_experiment_from_one_that_doesnt_exist_is_404(client: TestClient) -> None:
    assert client.post("/experiments", json={"name": "x", "from_experiment": "nope"}).status_code == 404


def test_an_experiment_says_what_it_chunked(client: TestClient) -> None:
    body = client.get("/experiments/done").json()
    assert (body["status"], body["chunked"]) == ("finished", [])
    assert client.get("/experiments/nope").status_code == 404


def test_an_unfinished_experiment_cant_be_applied(client: TestClient) -> None:
    assert client.post("/experiments/busy/apply").status_code == 409


def test_applying_an_experiment_makes_its_configuration_the_active_one(client: TestClient, store: Store) -> None:
    body = client.post("/experiments/done/apply").json()
    assert (body["origin"], body["experiment"], body["chunking"]["max_tokens"]) == ("experimento", "done", 126)
    assert store.config is not None and store.config.experiment == "done"


def test_without_a_configuration_the_default_is_shown(client: TestClient) -> None:
    body = client.get("/config").json()
    assert (body["origin"], body["chunking"]["chunker"], body["default"]["max_tokens"]) == ("defecto", "hybrid", 126)
    assert body["fixed"]["table_format"] == "triplets" and body["documents"] is None


def test_the_documents_are_counted_only_when_asked(client: TestClient) -> None:
    counts = client.get("/config", params={"documents": True}).json()["documents"]
    assert counts == {"with_active": 1, "with_other": 1, "not_chunked": 1}


def test_a_configuration_set_by_hand_is_checked(client: TestClient) -> None:
    assert client.put("/config", json={"chunker": "page", "max_tokens": 64}).status_code == 422
    assert client.put("/config", json={"tokenizer": "any/model"}).status_code == 422
    body = client.put("/config", json={"chunker": "hybrid", "max_tokens": 64}).json()
    assert (body["origin"], body["chunking"]["max_tokens"]) == ("manual", 64)


def test_patch_changes_only_what_comes(client: TestClient, store: Store) -> None:
    client.put("/config", json={"max_tokens": 64, "merge_peers": False})
    body = client.patch("/config", json={"max_tokens": 100}).json()
    assert (body["chunking"]["max_tokens"], body["chunking"]["merge_peers"]) == (100, False)
    body = client.patch("/config", json={"chunker": "page"}).json()
    assert body["chunking"] == {"chunker": "page", "tokenizer": PARAMETERS.tokenizer}


def test_delete_goes_back_to_the_default(client: TestClient, store: Store) -> None:
    store.config = ActiveConfig(RequestedChunking(max_tokens=64), ConfigOrigin.MANUAL, None, "2026")
    assert client.delete("/config").json()["origin"] == "defecto" and store.config is None


def test_a_run_without_a_configuration_is_409(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("chunking.domain.parameters.TOKENIZERS", ())
    answer = client.post("/runs", json={"sha256s": [A]})
    assert answer.status_code == 409 and "no configuration" in answer.json()["detail"]


@pytest.mark.parametrize(
    "body", [{"sha256s": ["nope"]}, {"sha256s": [A], "page": 1}, {"page": 0}, {"per_page": 501}, {"plan": {}}]
)
def test_a_run_that_cant_be_is_422(client: TestClient, body: dict[str, object]) -> None:
    assert client.post("/runs", json=body).status_code == 422


def test_simulating_a_run_counts_without_writing(client: TestClient, store: Store) -> None:
    body = client.post("/runs", json={"sha256s": [A, B], "simulate": True}).json()
    assert (body["progress"]["pending"], body["progress"]["unparsed"], body["status"]) == (1, 1, "finished")
    assert store.saved == []


def test_simulating_a_run_of_what_is_missing_reads_it_now(client: TestClient, store: Store) -> None:
    body = client.post("/runs", json={"per_page": 20, "simulate": True}).json()
    assert store.missing_asked == (PARAMETERS.fingerprint, 1, 20) and body["sha256s"] == [A, B]


def test_a_run_is_put_in_line_with_the_active_configuration(
    client: TestClient, store: Store, launched: list[str]
) -> None:
    store.config = ActiveConfig(RequestedChunking(max_tokens=64), ConfigOrigin.EXPERIMENT, "done", "2026")
    answer = client.post("/runs", json={"sha256s": [A, A]})
    assert answer.status_code == 202 and launched == [answer.json()["id"]]
    body = client.get(f"/runs/{answer.json()['id']}").json()
    assert (body["sha256s"], body["experiment"], body["parameters"]["max_tokens"]) == ([A], "done", 64)
    assert [r["id"] for r in client.get("/runs").json()] == [answer.json()["id"]]


def test_a_run_of_what_is_missing_takes_it_when_its_turn_comes(
    client: TestClient, store: Store, launched: list[str]
) -> None:
    answer = client.post("/runs", json={"page": 2, "per_page": 20}).json()
    assert (answer["frozen"], answer["sha256s"], answer["page"], answer["per_page"]) == (False, [], 2, 20)
    assert store.missing_asked is None  # read by the job, not now


def test_an_unknown_run_is_404_and_one_not_waiting_cant_leave_the_line(client: TestClient, launched: list[str]) -> None:
    assert client.get("/runs/nope").status_code == 404
    assert client.delete("/runs/nope").status_code == 404
    started = client.post("/runs", json={"sha256s": [A]}).json()["id"]
    assert client.delete(f"/runs/{started}").status_code == 409  # never queued: launch was replaced


def stored_run(status: RunStatus, parameters: ChunkingParameters = PARAMETERS) -> ChunkingRun:
    return ChunkingRun("r1", status, "2026", False, parameters, [A, B], chunked=[A], resumed=0)


def test_a_partial_run_is_resumed_with_the_same_id(client: TestClient, store: Store, launched: list[str]) -> None:
    store.stored_runs["r1"] = stored_run(RunStatus.PARTIAL)
    answer = client.post("/runs/r1/resume")
    assert answer.status_code == 202 and launched == ["r1"]
    body = answer.json()
    assert (body["id"], body["status"], body["sha256s"], body["resumed"]) == ("r1", "queued", [A, B], 1)
    assert client.post("/runs/r1/resume").status_code == 409  # it is in line already


@pytest.mark.parametrize("status", [RunStatus.FINISHED, RunStatus.RUNNING])
def test_only_a_partial_failed_or_interrupted_run_is_resumed(
    client: TestClient, store: Store, launched: list[str], status: RunStatus
) -> None:
    store.stored_runs["r1"] = stored_run(status)
    assert client.post("/runs/r1/resume").status_code == 409 and launched == []
    assert client.post("/runs/nope/resume").status_code == 404


def test_a_run_isnt_resumed_once_the_active_configuration_changed(
    client: TestClient, store: Store, launched: list[str]
) -> None:
    store.stored_runs["r1"] = stored_run(RunStatus.FAILED)
    store.config = ActiveConfig(RequestedChunking(max_tokens=64), ConfigOrigin.MANUAL, None, "2026")
    answer = client.post("/runs/r1/resume")
    assert answer.status_code == 409 and "configuration changed" in answer.json()["detail"] and launched == []


def test_a_partial_experiment_is_resumed_over_what_it_didnt_chunk(
    client: TestClient, store: Store, launched: list[str]
) -> None:
    answer = client.post("/experiments/half/resume")
    assert answer.status_code == 202 and launched == ["half"]
    assert (answer.json()["documents"], answer.json()["unparsed"]) == ([A], [B])
    assert store.saved[-1].nodes[0].properties["estado"] == "queued"


def test_a_finished_experiment_isnt_resumed_but_one_left_running_by_another_server_is(
    client: TestClient, launched: list[str]
) -> None:
    assert client.post("/experiments/done/resume").status_code == 409 and launched == []
    assert client.post("/experiments/busy/resume").status_code == 202 and launched == ["busy"]  # interrupted


def test_the_configuration_says_its_fingerprint(client: TestClient) -> None:
    assert client.get("/config").json()["fingerprint"] == PARAMETERS.fingerprint
