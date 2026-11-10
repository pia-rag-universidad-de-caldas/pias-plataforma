"""GET /data/file and /data/content: only chunkable files, never a path outside ingesta/. On temporary folders."""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ingesta.adapters import LocalFileAdapter, create_adapter
from ingesta.api import ApiSettings, create_app
from ingesta.config import sqlite_url
from ingesta.domain import Discovery, Ingestion
from ingesta.repository import DbCategoryRepository, DbFileRepository, DbRunRepository
from ingesta.tables import TABLES

PDF = b"%PDF-1.7 " + b"x" * 4000
CURRENT = "2024/01_Ene/Semana_02/020055/b.pdf"
COPY = "2024/01_Ene/Semana_01/111111/a.pdf"  # same content as CURRENT, older: a hash duplicate


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    base, ingest = tmp_path / "base", tmp_path / "ingesta"
    for relative in (COPY, CURRENT):
        (base / relative).parent.mkdir(parents=True)
        (base / relative).write_bytes(PDF)
    os.utime(base / COPY, (1_600_000_000, 1_600_000_000))  # older: CURRENT is the one that stays
    ingest.mkdir()
    (tmp_path / "secret.txt").write_text("no")
    memory = sqlite_url(str(ingest / "m.sqlite3"))
    data = create_adapter(memory, TABLES)
    try:
        source = LocalFileAdapter(str(base))
        repo = DbFileRepository(data)
        plan = Discovery.plan(source, set())
        Ingestion.run(
            plan, source, LocalFileAdapter(str(ingest)), repo, DbRunRepository(data), DbCategoryRepository(data)
        )
    finally:
        data.close()
    return TestClient(create_app(ApiSettings(str(base), str(ingest), memory)))


def test_a_chunkable_file_by_its_origin(client: TestClient) -> None:
    assert client.get("/data/file", params={"origin": CURRENT}).json()["origen"] == CURRENT


def test_a_chunkable_file_by_its_sha256(client: TestClient) -> None:
    sha256 = client.get("/data/file", params={"origin": CURRENT}).json()["sha256"]
    assert client.get("/data/file", params={"sha256": sha256}).json()["origen"] == CURRENT


def test_the_content_of_a_chunkable_file_says_its_type_and_name(client: TestClient) -> None:
    content = client.get("/data/content", params={"origin": CURRENT})
    assert content.status_code == 200 and content.content == PDF
    assert content.headers["content-type"] == "application/pdf"
    assert 'filename="b.pdf"' in content.headers["content-disposition"]


def test_a_hash_duplicate_is_not_served(client: TestClient) -> None:
    assert client.get("/data/file", params={"origin": COPY}).status_code == 404
    assert client.get("/data/content", params={"origin": COPY}).status_code == 404


@pytest.mark.parametrize("origin", ["../secret.txt", "2024/../../secret.txt", "/etc/passwd", "nope.pdf"])
def test_unsafe_or_unknown_origins_are_404(client: TestClient, origin: str) -> None:
    assert client.get("/data/file", params={"origin": origin}).status_code == 404
    assert client.get("/data/content", params={"origin": origin}).status_code == 404


@pytest.mark.parametrize("params", [{}, {"origin": CURRENT, "sha256": "ab"}])
def test_exactly_one_of_origin_and_sha256(client: TestClient, params: dict[str, str]) -> None:
    assert client.get("/data/file", params=params).status_code == 422


def test_data_lists_only_the_chunkable_ones(client: TestClient) -> None:
    page = client.get("/data").json()
    assert [f["origen"] for f in page["archivos"]] == [CURRENT] and page["reorganizado"] is not None
    assert client.get("/data", params={"type": "PDF", "year": 2024}).json()["total"] == 1
    assert client.get("/data", params={"code": "111111"}).json()["total"] == 0
