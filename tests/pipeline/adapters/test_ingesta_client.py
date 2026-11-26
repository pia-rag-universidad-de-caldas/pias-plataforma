"""IngestaClient against httpx.MockTransport: what it asks and how it reads the answer."""

from collections.abc import Callable

import httpx
import pytest

from pipeline.adapters import IngestaClient
from pipeline.models import Selection, UnavailableError

type Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler) -> httpx.Client:
    return httpx.Client(base_url="http://server", transport=httpx.MockTransport(handler))


def test_ingesta_page_sends_the_filters_and_reads_the_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get_list("type") == ["pdf", "docx"]
        assert request.url.params["year"] == "2024" and request.url.params["per_page"] == "20"
        body = {"reorganizado": "t", "paginas": 4, "archivos": [{"sha256": "a"}, {"sha256": "b"}]}
        return httpx.Response(200, json=body)

    page = IngestaClient(_client(handler), "/ingesta").page(
        Selection(all=True, types=("pdf", "docx"), year=2024), 2, 20
    )
    assert (page.sha256s, page.pages, page.reorganized) == (("a", "b"), 4, "t")


def test_ingesta_down_is_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detalle": "memory"})

    with pytest.raises(UnavailableError, match="memory"):
        IngestaClient(_client(handler), "/ingesta").has("a")


def test_an_ingestion_waits_for_another_one_and_reads_estado() -> None:
    answers = iter(
        [
            httpx.Response(409, json={"detalle": "another one runs"}),
            httpx.Response(202, json={"id": "i1", "estado": "en_curso"}),
            httpx.Response(200, json={"id": "i1", "estado": "en_curso"}),
            httpx.Response(200, json={"id": "i1", "estado": "terminada"}),
        ]
    )
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.method} {request.url.path}")
        return next(answers)

    outcome = IngestaClient(_client(handler), "/ingesta", sleep=lambda _: None).ingest()
    assert (outcome.id, outcome.status, outcome.succeeded) == ("i1", "terminada", True)
    assert seen == ["POST /ingesta/runs"] * 2 + ["GET /ingesta/runs/i1"] * 2


def test_a_failed_ingestion_didnt_succeed() -> None:
    answers = iter([httpx.Response(202, json={"id": "i1"}), httpx.Response(200, json={"estado": "fallida"})])
    outcome = IngestaClient(_client(lambda _: next(answers)), "/ingesta", sleep=lambda _: None).ingest()
    assert not outcome.succeeded and outcome.status == "fallida"
