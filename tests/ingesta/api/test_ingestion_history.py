"""The ingestions outlive the server (feature 039): saved in the memory, read back as GET /runs answered them. An older
memory gets the new table and keeps the rest."""

import sqlite3
import threading
from pathlib import Path

from fastapi.testclient import TestClient

from ingesta.adapters import SQLORMAdapter
from ingesta.api import ApiSettings, create_app
from ingesta.tables import TABLES


def settings(tmp_path: Path) -> ApiSettings:
    file = tmp_path / "base" / "2024" / "01_Enero" / "Semana_01" / "120501" / "a.pdf"
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(b"%PDF" + b"x" * 2000)
    return ApiSettings(str(tmp_path / "base"), str(tmp_path / "ingesta"), f"sqlite:///{tmp_path / 'm.sqlite3'}")


def finished_run(api: TestClient) -> str:
    """The run's id, once its thread ended: the registry says it ended just before the thread saves it in the memory, so
    reading (or changing) the file before that races with it."""
    id: str = api.post("/runs", json={}).json()["id"]
    for thread in threading.enumerate():
        if thread.name == f"ingesta-{id}":
            thread.join(10)
    assert api.get(f"/runs/{id}").json()["estado"] != "en_curso"
    return id


def test_an_ingestion_is_still_there_after_a_restart(tmp_path: Path) -> None:
    config = settings(tmp_path)
    id = finished_run(TestClient(create_app(config)))
    restarted = TestClient(create_app(config))
    assert [run["id"] for run in restarted.get("/runs").json()] == [id]
    found = restarted.get(f"/runs/{id}").json()
    assert found["estado"] == "terminada" and found["resultado"]["copiados"] == 1 and found["fin"]
    board = restarted.get("/processes").json()
    assert board["counts"]["finished"] == 1
    assert set(board["processes"][0]) == {"id", "module", "kind", "name", "state", "started", "finished",
                                          "duration_seconds"}  # fmt: skip


def test_one_that_was_running_when_the_server_stopped_was_interrupted(tmp_path: Path) -> None:
    config = settings(tmp_path)
    id = finished_run(TestClient(create_app(config)))
    with sqlite3.connect(tmp_path / "m.sqlite3") as connection:
        row = connection.execute("select detalle from corridas_api where id = ?", (id,)).fetchone()
        detail = (
            row[0]
            .replace('"estado":"terminada"', '"estado":"en_curso"')
            .replace('"estado": "terminada"', '"estado": "en_curso"')
        )
        connection.execute("update corridas_api set detalle = ?, estado = 'en_curso' where id = ?", (detail, id))
    restarted = TestClient(create_app(config))
    assert restarted.get(f"/runs/{id}").json()["estado"] == "interrumpida"
    assert restarted.get("/processes").json()["counts"]["interrupted"] == 1


def test_a_memory_older_than_the_table_gets_it_and_keeps_its_rows(tmp_path: Path) -> None:
    config = settings(tmp_path)
    finished_run(TestClient(create_app(config)))
    path = tmp_path / "m.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("drop table corridas_api")
        files = connection.execute("select count(*) from archivos").fetchone()[0]
    SQLORMAdapter.from_existing(config.memory, TABLES).close()
    with sqlite3.connect(path) as connection:
        assert connection.execute("select count(*) from corridas_api").fetchone()[0] == 0
        assert connection.execute("select count(*) from archivos").fetchone()[0] == files == 1
