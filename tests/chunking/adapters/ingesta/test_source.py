"""IngestaHttpSource (ChunkSource) over IngestaFilesClient (feature 026), against httpx.MockTransport: no server."""

import hashlib
from dataclasses import replace

import httpx
import pytest

from chunking.adapters import IngestaHttpSource
from chunking.adapters.http import Json
from chunking.models import DocumentError, DocumentFilter, SourceError

CONTENT = b"%PDF-1.7 test"
ROW: dict[str, Json] = {
    "origen": "2024/a.pdf",
    "destino": "vigentes/pdf/2024-a.pdf",
    "nombre": "a.pdf",
    "sha256": hashlib.sha256(CONTENT).hexdigest(),
    "tipo": "pdf",
    "anio": 2024,
    "codigo": "020055",
}


def source(pages: list[Json]) -> IngestaHttpSource:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ingesta/data":
            return httpx.Response(200, json=pages[int(request.url.params["page"]) - 1])
        if request.url.path == "/ingesta/data/file":
            return httpx.Response(200, json=ROW)
        return httpx.Response(200, content=CONTENT)

    return IngestaHttpSource(httpx.Client(base_url="http://server", transport=httpx.MockTransport(handler)), "/ingesta")


def page(rows: int, reorganized: str = "t1") -> Json:
    return {"archivos": [ROW] * rows, "paginas": 2, "reorganizado": reorganized}


def test_pages_are_source_documents() -> None:
    assert [[d.origin for d in p] for p in source([page(1), page(2)]).pages(DocumentFilter(), 10)] == [
        ["2024/a.pdf"],
        ["2024/a.pdf", "2024/a.pdf"],
    ]


def test_a_reorganization_between_pages_stops_the_run() -> None:
    pages = source([page(1), page(1, "t2")]).pages(DocumentFilter(), 10)
    assert len(next(pages)) == 1
    with pytest.raises(SourceError, match="stops after page 1"):
        next(pages)


def test_a_page_without_reorganizado() -> None:
    with pytest.raises(SourceError, match="without 'reorganizado'"):
        next(source([{"archivos": [], "paginas": 1}]).pages(DocumentFilter(), 10))


def test_find_and_content_checked_against_its_sha256() -> None:
    files = source([])
    document = files.find(str(ROW["sha256"]))
    assert files.content(document) == CONTENT
    with pytest.raises(DocumentError, match="doesn't have the sha256"):
        files.content(replace(document, sha256="00" * 32))
