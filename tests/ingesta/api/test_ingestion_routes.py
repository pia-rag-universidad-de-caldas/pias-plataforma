"""GET /source and POST /runs (feature 030): the server's base is the only source, and a whole ingestion started from
the API, on temporary folders."""

import time
from pathlib import Path

from fastapi.testclient import TestClient

from ingesta.api import ApiSettings, create_app
from ingesta.config import sqlite_url

PDF = b"%PDF-1.4\n" + b"x" * 2048  # over ALMOST_EMPTY_THRESHOLD: a chunkable pdf


def _write(root: Path, relative: str, content: bytes = PDF) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_the_api_always_reads_the_server_base(tmp_path: Path) -> None:
    memory = sqlite_url(str(tmp_path / "memoria.sqlite3"))
    missing = TestClient(create_app(ApiSettings(str(tmp_path / "base"), str(tmp_path / "ingesta"), memory)))
    assert missing.get("/source").json()["problemas"][0]["codigo"] == "no_encontrada"
    assert missing.post("/runs", json={}).status_code == 422
    assert missing.get("/source", params={"path": str(tmp_path)}).json()["ubicacion"] == str(tmp_path / "base")
    inside = TestClient(create_app(ApiSettings(str(tmp_path), str(tmp_path / "ingesta"), memory)))
    assert inside.get("/source").json()["problemas"][0]["codigo"] == "solapa_ingesta"


def _wait(client: TestClient, id: str) -> dict[str, object]:
    for _ in range(100):
        run: dict[str, object] = client.get(f"/runs/{id}").json()
        if run["estado"] != "en_curso":
            return run
        time.sleep(0.05)
    raise AssertionError("the ingestion didn't finish")


def test_ingestion_from_the_api(tmp_path: Path) -> None:
    base, ingest = tmp_path / "base", tmp_path / "ingesta"
    _write(base, "2024/11/Semana_04/671047/piaa.pdf")
    _write(base, "2024/11/Semana_04/671048/piaa.pdf", PDF + b"other")
    memory = sqlite_url(str(tmp_path / "memoria.sqlite3"))
    client = TestClient(create_app(ApiSettings(str(base), str(ingest), memory)))

    assert client.get("/source").json()["nuevos"] == 2
    assert client.post("/runs", json={"source": {"path": str(tmp_path)}}).status_code == 422  # no path: always base/
    assert client.post("/runs", json={"source": {"kind": "sql"}}).status_code == 501
    assert client.post("/runs", json={"move": True}).status_code == 422  # unknown key: there is no move
    simulated = client.post("/runs", json={"simulate": True})
    assert simulated.status_code == 200 and simulated.json()["copiaria"] == 2
    assert not ingest.exists()  # simulate touches nothing

    started = client.post("/runs", json={})
    assert started.status_code == 202
    run = _wait(client, started.json()["id"])
    assert run["estado"] == "terminada", run
    result = run["resultado"]
    assert isinstance(result, dict) and result["copiados"] == 2 and result["errores"] == 0
    assert result["carpetas"]["apto_chunking"] == 2
    assert sorted(p.name for p in (ingest / "vigentes" / "pdf").iterdir()) == [
        "2024-11-Semana_04-671047-piaa.pdf",
        "2024-11-Semana_04-671048-piaa.pdf",
    ]
    assert (base / "2024/11/Semana_04/671047/piaa.pdf").exists()  # the source stays intact
    assert client.get("/data").json()["total"] == 2  # the memory was created and filled

    again = client.post("/runs", json={})  # nothing new: a warning, the run is allowed and copies nothing
    assert _wait(client, again.json()["id"])["progreso"] == {"copiados": 0, "total": 0}
    assert [r["id"] for r in client.get("/runs").json()] == [again.json()["id"], started.json()["id"]]
