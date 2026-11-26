"""POST and GET /uploads (feature 049) on temporary folders: what is saved in base/, what is refused and the record."""

import sqlite3
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ingesta.adapters import SQLORMAdapter
from ingesta.api import ApiSettings, create_app
from ingesta.domain import Discovery
from ingesta.tables import TABLES

PDF = b"%PDF" + b"x" * 2000


def settings(tmp_path: Path) -> ApiSettings:
    return ApiSettings(str(tmp_path / "base"), str(tmp_path / "ingesta"), f"sqlite:///{tmp_path / 'm.sqlite3'}")


def api(tmp_path: Path) -> TestClient:
    return TestClient(create_app(settings(tmp_path)))


def test_a_pdf_is_saved_where_an_ingestion_finds_it_complete(tmp_path: Path) -> None:
    answer = api(tmp_path).post("/uploads", data={"code": "023560"}, files=[("files", ("mi doc.pdf", PDF))])
    assert answer.status_code == 200
    [result] = answer.json()
    assert result["estado"] == "guardado" and result["nombre"] == "mi doc.pdf"
    path = result["ruta"]
    assert (tmp_path / "base" / path).read_bytes() == PDF
    assert path.endswith("_mi_doc.pdf") and path.split("/")[3] == "023560"
    assert Discovery.read_structure(path, len(PDF)).complete


def test_a_content_already_uploaded_already_exists(tmp_path: Path) -> None:
    client = api(tmp_path)
    first = client.post("/uploads", data={"code": "023560"}, files=[("files", ("a.pdf", PDF))]).json()[0]
    again = client.post("/uploads", data={"code": "000000"}, files=[("files", ("b.pdf", PDF))]).json()[0]
    assert again["estado"] == "ya_existe" and again["ruta"] == first["ruta"] and again["sha256"] == first["sha256"]
    assert len(list((tmp_path / "base").rglob("*.pdf"))) == 1


def test_another_type_is_rejected_with_its_reason(tmp_path: Path) -> None:
    [result] = api(tmp_path).post("/uploads", data={"code": "023560"}, files=[("files", ("x.txt", PDF))]).json()
    assert result["estado"] == "rechazado" and "txt" in result["motivo"] and result["ruta"] is None
    assert not (tmp_path / "base").exists()


def test_a_name_with_folders_stays_inside_its_code_folder(tmp_path: Path) -> None:
    files = [("files[]", ("../../etc/evil.pdf", PDF))]
    [result] = api(tmp_path).post("/uploads", data={"code": "023560"}, files=files).json()
    assert result["estado"] == "guardado" and result["ruta"].endswith("_evil.pdf")
    assert result["ruta"].split("/")[3] == "023560" and ".." not in result["ruta"]


def test_a_code_that_isnt_six_digits_refuses_the_upload(tmp_path: Path) -> None:
    answer = api(tmp_path).post("/uploads", data={"code": "12ab56"}, files=[("files", ("a.pdf", PDF))])
    assert answer.status_code == 422 and "detalle" in answer.json()


def test_a_body_that_isnt_multipart_is_refused(tmp_path: Path) -> None:
    assert api(tmp_path).post("/uploads", json={"code": "023560"}).status_code == 415


def test_a_body_over_the_limit_is_refused(tmp_path: Path) -> None:
    client = TestClient(create_app(ApiSettings(**{**settings(tmp_path).__dict__, "raw_limit": 1000})))
    assert client.post("/uploads", data={"code": "023560"}, files=[("files", ("a.pdf", PDF))]).status_code == 413


def test_the_uploads_are_listed_newest_first(tmp_path: Path) -> None:
    client = api(tmp_path)
    client.post("/uploads", data={"code": "023560"}, files=[("files", ("a.pdf", PDF))])
    client.post("/uploads", data={"code": "023560"}, files=[("files", ("b.pdf", PDF + b"b"))])
    listed = client.get("/uploads").json()
    assert [u["nombre"] for u in listed] == ["b.pdf", "a.pdf"] and listed[0]["codigo"] == "023560"


def test_a_memory_older_than_the_uploads_table_gets_it(tmp_path: Path) -> None:
    config = settings(tmp_path)
    SQLORMAdapter.from_scratch(config.memory, TABLES).close()
    with sqlite3.connect(tmp_path / "m.sqlite3") as connection:
        connection.execute("drop table subidas")
    assert TestClient(create_app(config)).get("/uploads").json() == []


@pytest.mark.integration
def test_an_upload_is_ingested_and_its_content_then_already_exists(tmp_path: Path) -> None:
    client = api(tmp_path)
    saved = client.post("/uploads", data={"code": "023560"}, files=[("files", ("a.pdf", PDF))]).json()[0]["ruta"]
    id = client.post("/runs", json={}).json()["id"]
    for thread in threading.enumerate():
        if thread.name == f"ingesta-{id}":
            thread.join(10)
    assert [f["origen"] for f in client.get("/data").json()["archivos"]] == [saved]
    with sqlite3.connect(tmp_path / "m.sqlite3") as connection:
        connection.execute("delete from subidas")  # only the ingested file says it exists now
    again = client.post("/uploads", data={"code": "000000"}, files=[("files", ("otro.pdf", PDF))]).json()[0]
    assert again["estado"] == "ya_existe" and again["ruta"] == saved
