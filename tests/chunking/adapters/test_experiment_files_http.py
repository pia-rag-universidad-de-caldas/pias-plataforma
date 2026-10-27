"""ExperimentRunner.resolve with the selections of feature 028 (ingesta's page ranges, official JSON), over the real
HTTP adapters against httpx.MockTransport: no server."""

import hashlib
import json

import httpx

from chunking.adapters import GraphExperimentStore, IngestaHttpSource
from chunking.adapters.http import Json
from chunking.domain import ExperimentRunner
from chunking.models import (
    ConversionParameters,
    ConvertedDocument,
    DocumentFilter,
    DocumentSection,
    Element,
    ElementKind,
    ExperimentRequest,
    FileSelection,
    Inclusion,
    JsonSelection,
    PageRange,
    TableMode,
)

CONVERSION = ConversionParameters(1, False, True, TableMode.ACCURATE, Inclusion(True, True, False, False, False), "2")
CONTENT = ConvertedDocument("t", [DocumentSection("Objetivos", 1, [1], [Element(ElementKind.PARAGRAPH, "x", [1])])])


def sha(n: int) -> str:
    return hashlib.sha256(str(n).encode()).hexdigest()


def row(n: int) -> Json:
    return {
        "origen": f"2024/{n}.pdf",
        "destino": f"v/{n}.pdf",
        "nombre": f"{n}.pdf",
        "sha256": sha(n),
        "tipo": "pdf",
        "anio": 2024,
        "codigo": "020055",
    }


def official(n: int, content: bool = True) -> Json:
    properties = {**json.loads(json.dumps(row(n)))}
    if content:
        properties |= {"contenido": CONTENT.to_json(), "fingerprint_conversion": "f1", "conversion": "{}"}
    return {"label": "JSON", "id": sha(n), "properties": properties}


def handler(request: httpx.Request) -> httpx.Response:
    path, params = request.url.path, request.url.params
    if path == "/ingesta/data":  # 3 pages of 2
        page = int(params["page"])
        rows = [row(2 * page - 1), row(2 * page)]
        return httpx.Response(200, json={"archivos": rows, "paginas": 3, "reorganizado": "t1"})
    if path == "/data/nodes/JSON":  # 2 pages: the second has a JSON never promoted
        page = int(params["page"])
        nodes = [official(1), official(2)] if page == 1 else [official(3, content=False)]
        return httpx.Response(200, json={"nodes": nodes, "pages": 2})
    if path == f"/data/nodes/JSON/{sha(1)}":
        return httpx.Response(200, json=official(1))
    return httpx.Response(404, json={"detail": "none"})


def resolve(files: FileSelection) -> tuple[list[str], list[str]]:
    client = httpx.Client(base_url="http://server", transport=httpx.MockTransport(handler))
    request = ExperimentRequest("e", "", files, CONVERSION, None)
    resolution = ExperimentRunner.resolve(
        IngestaHttpSource(client, "/ingesta"), GraphExperimentStore(client, "/data"), request, 2
    )
    return [f.document.origin for f in resolution.files], [f.error for f in resolution.failures]


def test_ingesta_page_range() -> None:
    files = FileSelection(filter=DocumentFilter(["pdf"]), pages=PageRange(2, 3), per_page=2)
    assert resolve(files) == (["2024/3.pdf", "2024/4.pdf", "2024/5.pdf", "2024/6.pdf"], [])


def test_ingesta_all() -> None:
    assert len(resolve(FileSelection(filter=DocumentFilter(), all=True))[0]) == 6


def test_official_json_without_content_fails_alone() -> None:
    origins, errors = resolve(FileSelection(from_json=JsonSelection(all=True)))
    assert origins == ["2024/1.pdf", "2024/2.pdf"]
    assert len(errors) == 1 and "no converted content" in errors[0]


def test_official_json_by_sha256() -> None:
    client = httpx.Client(base_url="http://server", transport=httpx.MockTransport(handler))
    request = ExperimentRequest(
        "e", "", FileSelection(from_json=JsonSelection(sha256s=[sha(1), sha(9)])), CONVERSION, None
    )
    resolution = ExperimentRunner.resolve(
        IngestaHttpSource(client, "/ingesta"), GraphExperimentStore(client, "/data"), request, 2
    )
    [file] = resolution.files
    assert file.reused and file.conversion_id == f"{sha(1)}:f1"
    assert file.official is not None and file.official.content == CONTENT
    assert [f.sha256 for f in resolution.failures] == [sha(9)]
