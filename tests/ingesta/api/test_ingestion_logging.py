"""What an ingestion started from the API leaves in the logs, with its id."""

import logging
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ingesta.api import ApiSettings, create_app, ingestion_registry, ingestion_worker
from ingesta.config import sqlite_url
from ingesta.models import FileFailure, MemoryStoreError

LOGGER = "ingesta.api"
PDF = b"%PDF-1.4\n" + b"x" * 2048
FAILED = "fallida"


def _thread_ended(id: str) -> None:
    """A run shows as ended a moment before its thread stores it and says so."""
    for thread in threading.enumerate():
        if thread.name == f"ingesta-{id}":
            thread.join(5)


def _ingest(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> tuple[str, str]:
    """A whole ingestion of one file: its id and how it ended."""
    file = tmp_path / "base/2024/01/s1/020055/uno.pdf"
    file.parent.mkdir(parents=True)
    file.write_bytes(PDF)
    settings = ApiSettings(str(tmp_path / "base"), str(tmp_path / "ingesta"), sqlite_url(str(tmp_path / "m.sqlite3")))
    client = TestClient(create_app(settings))
    with caplog.at_level(logging.INFO, logger=LOGGER):
        id: str = client.post("/runs", json={}).json()["id"]
        for _ in range(200):
            state: str = client.get(f"/runs/{id}").json()["estado"]
            if state != "en_curso":
                _thread_ended(id)
                return id, state
            time.sleep(0.02)
    raise AssertionError("the ingestion didn't finish")


def _infos(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]


def test_an_ingestion_says_when_it_starts(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    id, _ = _ingest(tmp_path, caplog)
    assert any(id in line and "started" in line for line in _infos(caplog))


def test_an_ingestion_ends_with_its_counters(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    id, _ = _ingest(tmp_path, caplog)
    assert any(id in line and "finished" in line and "copied=1" in line for line in _infos(caplog))


def test_a_failed_file_says_which_and_why(caplog: pytest.LogCaptureFixture) -> None:
    observer = ingestion_worker._RegistryObserver(Ignored(), "run7")
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        observer.failed(FileFailure("2024/uno.pdf", "no space left"))
    assert "run7" in caplog.text
    assert "2024/uno.pdf" in caplog.text
    assert "no space left" in caplog.text


class Ignored(ingestion_registry.IngestionRegistry):
    def failure(self, id: str, failure: FileFailure) -> None:
        pass


def test_a_failed_ingestion_is_an_error(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    def down(*_: object) -> None:
        raise MemoryStoreError("the memory is down")

    monkeypatch.setattr(ingestion_worker, "create_adapter", down)
    id, state = _ingest(tmp_path, caplog)
    assert state == FAILED
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert any(id in line and "the memory is down" in line for line in errors)
