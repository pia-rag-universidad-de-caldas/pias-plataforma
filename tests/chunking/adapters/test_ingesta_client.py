"""IngestaFilesClient and ingesta's mappers (feature 026), against httpx.MockTransport: no server."""

from collections.abc import Callable

import httpx
import pytest

from chunking.adapters.http import Json
from chunking.adapters.ingesta import IngestaFilesClient, document, filter_params
from chunking.models import DocumentError, DocumentFilter, SourceDocument, SourceError

ROW: dict[str, Json] = {
    "origen": "2024/01_Enero/Semana_03/020055/a.pdf",
    "destino": "vigentes/pdf/2024-01_Enero-Semana_03-020055-a.pdf",
    "nombre": "a.pdf",
    "sha256": "ab" * 32,
    "tipo": "pdf",
    "anio": 2024,
    "codigo": "020055",
    "mime": "application/pdf",
}


def files(handler: Callable[[httpx.Request], httpx.Response]) -> IngestaFilesClient:
    http = httpx.Client(base_url="http://server", transport=httpx.MockTransport(handler))
    return IngestaFilesClient(http, "/ingesta")


def test_document_maps_a_file_record() -> None:
    assert document(ROW) == SourceDocument(
        origin=ROW["origen"],
        target=ROW["destino"],
        name="a.pdf",
        sha256="ab" * 32,
        file_type="pdf",
        year=2024,
        code="020055",
    )


def test_document_without_optional_values() -> None:
    mapped = document({**ROW, "sha256": None, "anio": None, "codigo": ""})
    assert (mapped.sha256, mapped.year, mapped.code) == (None, None, None)


@pytest.mark.parametrize("row", [[], "file", {k: v for k, v in ROW.items() if k != "origen"}, {**ROW, "anio": "x"}])
def test_document_rejects_a_bad_row(row: Json) -> None:
    with pytest.raises(SourceError):
        document(row)


def test_filter_params_repeats_type_and_skips_what_is_not_set() -> None:
    assert filter_params(DocumentFilter(types=["pdf", "docx"], year=2024, code="020055")) == (
        ("type", "pdf"),
        ("type", "docx"),
        ("year", 2024),
        ("code", "020055"),
    )
    assert filter_params(DocumentFilter()) == ()


def test_pages_walks_data_with_the_filter() -> None:
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        page = int(request.url.params["page"])
        return httpx.Response(200, json={"archivos": [ROW] * page, "paginas": 2, "reorganizado": "t"})

    bodies = list(files(handler).pages(DocumentFilter(types=["pdf"]), 50))
    assert [len(b["archivos"]) for b in bodies] == [1, 2]
    assert [u.path for u in seen] == ["/ingesta/data"] * 2
    assert seen[1].params.multi_items() == [("type", "pdf"), ("page", "2"), ("per_page", "50")]


@pytest.mark.parametrize("status", [404, 422, 503])
def test_an_error_of_data_stops_the_run(status: int) -> None:
    client = files(lambda _: httpx.Response(status, json={"detalle": "nope"}))
    with pytest.raises(SourceError):
        client.page(DocumentFilter(), 1, 10)


def test_file_by_sha256() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert (request.url.path, request.url.params["sha256"]) == ("/ingesta/data/file", "ab" * 32)
        return httpx.Response(200, json=ROW)

    assert files(handler).file("ab" * 32) == ROW


def test_a_missing_file_fails_only_that_document() -> None:
    client = files(lambda _: httpx.Response(404, json={"detalle": "the origin 'x' isn't registered"}))
    with pytest.raises(DocumentError, match="isn't registered"):
        client.file("00" * 32)
    with pytest.raises(DocumentError, match="isn't registered"):
        client.content("x")


def test_content_is_the_bytes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert (request.url.path, request.url.params["origin"]) == ("/ingesta/data/content", "a/b.pdf")
        return httpx.Response(200, content=b"%PDF-1.7")

    assert files(handler).content("a/b.pdf") == b"%PDF-1.7"


def test_ingesta_down_is_a_source_error() -> None:
    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    with pytest.raises(SourceError, match="GET /ingesta/data/file: Connection refused"):
        files(refused).file("00" * 32)
