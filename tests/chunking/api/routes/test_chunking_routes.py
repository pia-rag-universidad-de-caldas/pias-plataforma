"""The routes of chunking (features 043 and 045) over fake stores: experiments, the active configuration and the runs.
No data, no docling-core: what would run in line is caught before it starts."""

import json
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
    ExperimentDependents,
    ExperimentProgress,
    ExperimentRecord,
    ExperimentRequest,
    ExperimentStatus,
    GraphBatch,
    ParsedDocument,
    RequestedChunking,
    RunStatus,
)

A, B, C = "a" * 64, "b" * 64, "c" * 64
PARAMETERS = Parameters.resolve(RequestedChunking(), "2")


def record(id: str, status: ExperimentStatus = ExperimentStatus.FINISHED, all: bool = False) -> ExperimentRecord:
    asked = ExperimentRequest(id, "", PARAMETERS, [] if all else [A, B], all=all)
    stored = ExperimentGraph.experiment(id, asked, 0, "").nodes[0].properties
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
        all=all,
    )


class Store:
    """ExperimentStore and ConfigStore and RunStore, all in memory."""

    def __init__(self) -> None:
        self.records = {
            "done": record("done"),
            "busy": record("busy", ExperimentStatus.RUNNING),
            "half": record("half", ExperimentStatus.PARTIAL),
            "every": record("every", ExperimentStatus.INTERRUPTED, all=True),
        }
        self.saved: list[GraphBatch] = []
        self.config: ActiveConfig | None = None
        self.stored_runs: dict[str, ChunkingRun] = {}
        self.missing_asked: tuple[str, int | None, int | None] | None = None
        self.depending: dict[str, ExperimentDependents] = {}
        self.parsed = 3  # parsed JSON data has (feature 059)

    def document(self, sha256: str) -> ParsedDocument | None:
        return ParsedDocument(sha256, "parseado", "p", "stored") if sha256 in (A, C) else None

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

    def dependents(self, id: str) -> ExperimentDependents:
        return self.depending.get(id, ExperimentDependents([], []))

    def missing(self, fingerprint: str, page: int | None, per_page: int | None) -> list[str]:
        self.missing_asked = (fingerprint, page, per_page)
        return [A, B]

    def parsed_documents(self) -> list[str]:
        return [A] * self.parsed

    def parsed_count(self) -> int:
        return self.parsed

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
        {"name": "x", "sha256s": [A], "all": True},
        {"name": "x", "from_experiment": "done", "all": True},
        {"name": "x", "all": False},
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


@pytest.fixture
def lines(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    """The arguments of what would have been put in line (feature 059: the resolution, or None)."""
    found: list[tuple[Any, ...]] = []
    monkeypatch.setattr(import_module("chunking.api.routes.experiments"), "launch", lambda *args: found.append(args))
    return found


def test_simulating_an_experiment_of_every_document_only_counts(client: TestClient, store: Store) -> None:
    answer = client.post("/experiments", json={"name": "x", "all": True, "simulate": True})
    assert answer.status_code == 200
    body = answer.json()
    assert (body["all"], body["total"], body["documents"], body["unparsed"]) == (True, 3, [], [])
    assert store.saved == []


def test_an_experiment_of_every_document_takes_them_when_its_turn_comes(
    client: TestClient, store: Store, lines: list[tuple[Any, ...]]
) -> None:
    answer = client.post("/experiments", json={"name": "x", "all": True})
    assert answer.status_code == 202 and answer.json()["total"] == 3
    [(_, _, id, _, _, request, resolution)] = lines
    assert (id, request.all, resolution) == (answer.json()["id"], True, None)
    assert '"all": true' in str(store.saved[0].nodes[0].properties["documentos"])


def test_an_experiment_of_every_document_without_any_parsed_is_409(client: TestClient, store: Store) -> None:
    store.parsed = 0
    assert client.post("/experiments", json={"name": "x", "all": True}).status_code == 409


def test_an_experiment_of_every_document_says_so(client: TestClient) -> None:
    assert client.get("/experiments/every").json()["all"] is True
    assert client.get("/experiments/done").json()["all"] is False
    assert {e["id"]: e["all"] for e in client.get("/experiments").json()}["every"] is True


def test_resuming_an_experiment_of_every_document_takes_them_again_when_its_turn_comes(
    client: TestClient, store: Store, lines: list[tuple[Any, ...]]
) -> None:
    answer = client.post("/experiments/every/resume")
    assert answer.status_code == 202
    assert (answer.json()["all"], answer.json()["documents"], answer.json()["total"]) == (True, [], 3)
    [arguments] = lines
    assert (arguments[5].all, arguments[6], arguments[7]) == (True, None, [])


def test_an_experiment_from_one_that_doesnt_exist_is_404(client: TestClient) -> None:
    assert client.post("/experiments", json={"name": "x", "from_experiment": "nope"}).status_code == 404


def test_an_experiment_says_what_it_chunked(client: TestClient) -> None:
    body = client.get("/experiments/done").json()
    assert (body["status"], body["chunked"]) == ("finished", [])
    assert client.get("/experiments/nope").status_code == 404


def test_an_experiment_without_dependents_is_deleted(client: TestClient, store: Store) -> None:
    assert client.delete("/experiments/done").status_code == 204 and "done" not in store.records
    assert client.delete("/experiments/done").status_code == 404


def test_an_experiment_an_embeddings_one_uses_is_409_even_with_force(client: TestClient, store: Store) -> None:
    """Feature 055 part b: its EXP_EMBEDDINGS would point at nothing; that one is deleted first, in embeddings."""
    store.depending["done"] = ExperimentDependents(["emb1"], ["it1"])
    for path in ("/experiments/done", "/experiments/done?force=true"):
        answer = client.delete(path)
        assert answer.status_code == 409 and "emb1" in answer.json()["detail"]
    assert "done" in store.records


def test_an_experiment_a_pipeline_run_links_is_deleted_only_with_force(client: TestClient, store: Store) -> None:
    store.depending["done"] = ExperimentDependents([], ["it1"])
    answer = client.delete("/experiments/done")
    assert answer.status_code == 409 and "it1" in answer.json()["detail"] and "done" in store.records
    assert client.delete("/experiments/done?force=true").status_code == 204 and "done" not in store.records


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


def test_cancelling_a_run_asks_it_to_stop_and_an_unknown_one_is_404(client: TestClient, launched: list[str]) -> None:
    assert client.post("/runs/nope/cancel").status_code == 404
    started = client.post("/runs", json={"sha256s": [A]}).json()["id"]  # never queued: launch was replaced
    answer = client.post(f"/runs/{started}/cancel")
    assert answer.status_code == 200 and answer.json()["cancel_requested"] is True


# Feature 062: documents added to an experiment, and `fit`.


def test_adding_documents_puts_the_new_parsed_ones_in_its_list(
    client: TestClient, store: Store, lines: list[tuple[Any, ...]]
) -> None:
    answer = client.post("/experiments/done/documents", json={"sha256s": [A, C, "d" * 64]})
    assert answer.status_code == 202
    assert {k: answer.json()[k] for k in ("added", "already", "unparsed", "total")} == {
        "added": [C],
        "already": [A],
        "unparsed": ["d" * 64],
        "total": 3,
    }
    [arguments] = lines
    assert (arguments[5].sha256s, arguments[5].parameters) == ([A, B, C], PARAMETERS)  # its own configuration
    stored = store.saved[-1].nodes[0].properties
    assert stored["estado"] == "queued" and f'"{C}"' in str(stored["documentos"])
    assert [s["kind"] for s in json.loads(str(stored["selecciones"]))] == ["created", "added"]


def test_simulating_an_addition_stores_nothing(client: TestClient, store: Store, launched: list[str]) -> None:
    answer = client.post("/experiments/done/documents", json={"sha256s": [C], "simulate": True})
    assert answer.status_code == 200 and answer.json()["status"] == "simulated"
    assert store.saved == [] and launched == []


@pytest.mark.parametrize(("id", "code"), [("nope", 404), ("done", 409)])
def test_an_addition_without_anything_new_or_experiment_is_refused(client: TestClient, id: str, code: int) -> None:
    assert client.post(f"/experiments/{id}/documents", json={"sha256s": [A, B]}).status_code == code


def test_documents_cant_be_added_while_it_runs(client: TestClient, launched: list[str]) -> None:
    client.post("/experiments/half/resume")  # now in line in this server
    assert client.post("/experiments/half/documents", json={"sha256s": [C]}).status_code == 409


def test_an_experiment_of_before_says_its_creation_as_its_only_selection(client: TestClient) -> None:
    [selection] = client.get("/experiments/done").json()["selections"]
    assert (selection["kind"], selection["at"]) == ("created", "2026")


MINI, E5 = PARAMETERS.tokenizer, "intfloat/multilingual-e5-base"
FIT = [{"tokenizer": MINI, "max_tokens": 126}, {"tokenizer": E5, "max_tokens": 500}]


def test_the_active_configuration_can_fit_several_tokenizers(client: TestClient, store: Store) -> None:
    body = client.put("/config", json={"fit": FIT}).json()
    assert body["chunking"] == {"chunker": "hybrid", "merge_peers": True, "fit": FIT}
    assert store.config is not None and store.config.requested.fit is not None


@pytest.mark.parametrize(
    "body", [{"fit": FIT, "max_tokens": 64}, {"fit": FIT, "chunker": "page"}, {"fit": []}, {"fit": [FIT[0]] * 2}]
)
def test_a_fit_that_cant_be_is_422(client: TestClient, body: dict[str, object]) -> None:
    assert client.put("/config", json=body).status_code == 422


def test_patch_keeps_the_fit_unless_a_tokenizer_or_max_tokens_comes(client: TestClient) -> None:
    client.put("/config", json={"fit": FIT})
    assert client.patch("/config", json={"merge_peers": False}).json()["chunking"]["fit"] == FIT
    body = client.patch("/config", json={"max_tokens": 100}).json()["chunking"]
    assert "fit" not in body and body["max_tokens"] == 100
