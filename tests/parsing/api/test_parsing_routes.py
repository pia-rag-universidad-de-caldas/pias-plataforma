"""The parsing API (feature 042) on TestClient: data is a dict behind an httpx.MockTransport, the parser a fake."""

import base64
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass

import httpx
import pytest
from fakes import FakeData
from fastapi.testclient import TestClient

from common.http import Json
from parsing.adapters import HttpSession
from parsing.api import ApiSettings, create_app
from parsing.models import PageCoverage, ParsedOutput, Parser, StoredParse

A, B = "a" * 64, "b" * 64


class FakeParser(Parser):
    def __init__(self, installed: bool = True) -> None:
        self._installed = installed

    def available(self) -> bool:
        return self._installed

    def ocr_available(self) -> bool:
        return self._installed

    def version(self) -> str | None:
        return "2.148.0" if self._installed else None

    def parse(self, name: str, content: bytes, previous: StoredParse | None = None) -> ParsedOutput:
        return ParsedOutput({"schema_name": "DoclingDocument", "name": name}, PageCoverage(1, 1))


@dataclass(frozen=True)
class FakeSettings(ApiSettings):
    data: FakeData | None = None

    def session(self) -> HttpSession:
        assert self.data is not None
        return HttpSession(self.self_url, self.data_path, transport=httpx.MockTransport(self.data.handle))


@pytest.fixture
def data(fake_data: FakeData) -> FakeData:
    content = base64.b64encode(b"%PDF").decode()
    fake_data.nodes[("RAW", A)] = {"nombre": "a.pdf", "tipo": "pdf", "codigo": "020055", "contenido": content}
    return fake_data


@pytest.fixture
def client(data: FakeData) -> Iterator[TestClient]:
    with TestClient(create_app(FakeSettings("http://server", data=data), FakeParser())) as test_client:
        yield test_client


def wait(client: TestClient, id: str) -> Json:
    for _ in range(200):
        run = client.get(f"/runs/{id}").json()
        if run["status"] in ("finished", "failed", "cancelled"):
            return run
        time.sleep(0.01)
    raise AssertionError(f"the run {id} didn't end")


@pytest.mark.integration
def test_scenario_a_run_parses_what_data_has_and_says_what_it_doesnt(client: TestClient, data: FakeData) -> None:
    started = client.post("/runs", json={"sha256s": [A, B, A]})
    assert started.status_code == 202
    run = wait(client, started.json()["id"])
    assert (run["status"], run["parsed"]) == ("finished", [A])
    assert [d["state"] for d in run["documents"]] == ["parsed", "missing"]
    assert data.nodes[("RAW", A)]["estado_parseo"] == "parseado" and ("JSON", A) in data.nodes
    assert client.get("/runs").json()[0]["id"] == run["id"]
    again = wait(client, client.post("/runs", json={"sha256s": [A]}).json()["id"])
    assert again["progress"]["skipped"] == 1 and again["parsed"] == [A]  # skipped: it already has its JSON


def test_a_run_without_sha256s_takes_every_current_raw_still_to_parse(client: TestClient) -> None:
    run = client.post("/runs", json={}).json()
    assert [d["sha256"] for d in run["documents"]] == [A]
    assert wait(client, run["id"])["progress"]["parsed"] == 1
    again = client.post("/runs", json={}).json()
    assert again["documents"] == []  # nothing left: the run has nothing to do


@pytest.mark.parametrize(
    "body",
    [{"sha256s": ["nope"]}, {"sha256s": [A], "conversion": {}}],
    ids=["not a sha256", "unknown key"],
)
def test_a_run_takes_sha256s_and_nothing_else(client: TestClient, body: dict[str, object]) -> None:
    assert client.post("/runs", json=body).status_code == 422


def test_without_docling_a_run_is_503_and_the_health_says_so(data: FakeData) -> None:
    with TestClient(create_app(FakeSettings("http://server", data=data), FakeParser(installed=False))) as client:
        assert client.post("/runs", json={"sha256s": [A]}).status_code == 503
        assert client.get("/health").json()["docling"] == "missing"


def test_the_config_is_the_fixed_one_with_its_fingerprint(client: TestClient) -> None:
    body = client.get("/config").json()
    assert body["config"]["table_mode"] == "accurate" and body["config"]["heading_hierarchy"] is True
    assert body["fingerprint"] and body["docling"] == "2.148.0"


def test_an_unknown_run_is_404(client: TestClient) -> None:
    assert client.get("/runs/nope").status_code == 404
    assert client.delete("/runs/nope").status_code == 404


class GatedParser(FakeParser):
    """Parses only when the test opens its gate (feature 056: a run is cancelled while it parses)."""

    def __init__(self) -> None:
        super().__init__()
        self.parsing, self.gate = threading.Event(), threading.Event()

    def parse(self, name: str, content: bytes, previous: StoredParse | None = None) -> ParsedOutput:
        self.parsing.set()
        self.gate.wait(5)
        return super().parse(name, content, previous)


@pytest.mark.integration
def test_cancel_lets_the_running_document_end_and_parses_no_more(data: FakeData) -> None:
    data.nodes[("RAW", B)] = dict(data.nodes[("RAW", A)])
    parser = GatedParser()
    with TestClient(create_app(FakeSettings("http://server", data=data), parser)) as client:
        id = client.post("/runs", json={"sha256s": [A, B]}).json()["id"]
        assert parser.parsing.wait(5)
        asked = client.post(f"/runs/{id}/cancel")
        assert asked.status_code == 200 and asked.json()["cancel_requested"] is True
        parser.gate.set()
        run = wait(client, id)
        assert (run["status"], run["parsed"]) == ("cancelled", [A])  # the one it was on ended and stays
        assert [d["state"] for d in run["documents"]] == ["parsed", "waiting"]
        assert client.post(f"/runs/{id}/cancel").status_code == 409  # it already ended


def test_cancelling_an_unknown_run_is_404(client: TestClient) -> None:
    assert client.post("/runs/nope/cancel").status_code == 404
