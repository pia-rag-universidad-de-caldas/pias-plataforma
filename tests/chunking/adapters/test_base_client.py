"""BaseHttpClient and paginate (feature 026), against httpx.MockTransport: no server."""

from collections.abc import Callable

import httpx
import pytest

from chunking.adapters.http import BaseHttpClient, ErrorPolicy, Json, paginate, segment


class Down(Exception):
    pass


class Refused(Exception):
    pass


class Missing(Exception):
    pass


type Handler = Callable[[httpx.Request], httpx.Response]


def client(handler: Handler) -> BaseHttpClient:
    http = httpx.Client(base_url="http://server", transport=httpx.MockTransport(handler), timeout=1)
    return BaseHttpClient(http, "/module/", ErrorPolicy("module", Down, Refused))


def answer(status: int, body: Json = None, text: str | None = None) -> Handler:
    return lambda _: httpx.Response(status, text=text) if text is not None else httpx.Response(status, json=body)


def test_route_is_under_the_path_with_its_params() -> None:
    seen: list[httpx.URL] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url)
        return httpx.Response(200, json={"ok": True})

    assert client(handler)._get("/things", (("type", "pdf"), ("type", "doc"), ("page", 2))) == {"ok": True}
    assert seen[0].path == "/module/things"
    assert seen[0].params.get_list("type") == ["pdf", "doc"]
    assert seen[0].params["page"] == "2"


def test_segment_escapes_slashes() -> None:
    assert segment("a/b c") == "a%2Fb%20c"


def test_404_is_none_or_the_given_error_with_the_module_message() -> None:
    base = client(answer(404, {"detalle": "no such file"}))
    assert base._get("/x") is None
    with pytest.raises(Missing, match="no such file"):
        base._get("/x", not_found=Missing)


@pytest.mark.parametrize("status", [400, 409, 422])
def test_other_4xx_is_rejected(status: int) -> None:
    with pytest.raises(Refused, match=f"module rejected GET /module/x: {status} bad"):
        client(answer(status, {"detail": "bad"}))._get("/x")


@pytest.mark.parametrize("status", [500, 503])
def test_5xx_is_unavailable(status: int) -> None:
    with pytest.raises(Down, match=f"GET /module/x: {status} Neo4j is down"):
        client(answer(status, {"detail": "Neo4j is down"}))._get("/x")


def test_network_error_and_timeout_are_unavailable() -> None:
    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused", request=request)

    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(Down, match="Connection refused"):
        client(refused)._get("/x")
    with pytest.raises(Down, match="no answer within 1"):
        client(slow)._get("/x")


def test_an_answer_that_is_not_json_is_unavailable() -> None:
    with pytest.raises(Down, match="module answered something that isn't JSON"):
        client(answer(200, text="<html>"))._get("/x")


def test_detail_falls_back_to_the_text() -> None:
    with pytest.raises(Refused, match="plain error"):
        client(answer(400, text="plain error"))._get("/x")


def test_paginate_asks_each_page_only_when_the_previous_was_consumed() -> None:
    asked: list[int] = []

    def fetch(page: int) -> Json:
        asked.append(page)
        return {"pages": 3 if page == 1 else 99, "items": [page]}

    pages = paginate(fetch, "pages", Down)
    assert asked == []
    assert next(pages)["items"] == [1]
    assert asked == [1]
    assert [p["items"] for p in pages] == [[2], [3]]  # the number of pages is the one of the first answer
    assert asked == [1, 2, 3]


def test_paginate_with_no_pages_yields_the_first_answer_only() -> None:
    assert list(paginate(lambda page: {"pages": 0, "items": []}, "pages", Down)) == [{"pages": 0, "items": []}]


@pytest.mark.parametrize("body", [None, [], {"items": []}, {"pages": "many"}])
def test_paginate_rejects_unexpected_pages(body: Json) -> None:
    with pytest.raises(Down):
        list(paginate(lambda page: body, "pages", Down))


def test_paginate_a_range_starts_at_first_and_stops_at_last() -> None:
    asked: list[int] = []

    def fetch(page: int) -> Json:
        asked.append(page)
        return {"pages": 9, "items": [page]}

    assert [p["items"] for p in paginate(fetch, "pages", Down, first=3, last=5)] == [[3], [4], [5]]
    assert asked == [3, 4, 5]


def test_paginate_a_range_ends_with_the_listing() -> None:
    assert [p["items"] for p in paginate(lambda page: {"pages": 4, "items": [page]}, "pages", Down, 3, 10)] == [
        [3],
        [4],
    ]


def test_paginate_a_range_beyond_the_last_page_yields_nothing() -> None:
    assert list(paginate(lambda page: {"pages": 2, "items": []}, "pages", Down, first=5)) == []
