"""Autocomplete (feature 035): each field reads its values from what exists, over HTTP; recent ids first. Against a
fake server (httpx.MockTransport) that answers what each module would."""

from collections.abc import Callable

import httpx

from server.console.bodies import JsonValue
from server.console.catalog import Operation
from server.console.client import ApiClient
from server.console.suggestions import Suggester

type Catalog = dict[str, tuple[Operation, ...]]
type Find = Callable[[str, str, str], Operation]

ANSWERS: dict[str, JsonValue] = {
    "/data/nodes/PIAA": {"nodes": [{"label": "PIAA", "id": "120501", "properties": {"nombre": "Cálculo I"}}]},
    "/chunking/experiments": [{"id": "e1", "name": "prueba", "status": "finished", "created": "2026"}],
    "/chunking/experiments/e1/scores": {"scores": [{"id": "s1", "author": "ana", "created": "2026"}]},
    "/ingesta/stats/years": {"filas_anios": [{"anio": 2024, "archivos": 10}]},
    "/ingesta/data": {
        "archivos": [{"origen": "2024/x.pdf", "sha256": "abc", "codigo": "120501", "nombre": "x.pdf"}],
        "paginas": 1,
    },
    "/pipeline/runs/p1": {
        "stage": "chunking",
        "template": {"stages": [{"id": "conversion", "actor": "lab"}, {"id": "chunking", "actor": "lab2"}]},
    },
}


def fake() -> ApiClient:
    def answer(request: httpx.Request) -> httpx.Response:
        found = ANSWERS.get(request.url.path)
        return httpx.Response(200, json=found) if found is not None else httpx.Response(404, json={})

    return ApiClient(httpx.Client(transport=httpx.MockTransport(answer), base_url="http://test"))


def values(find: Find, module: str, method: str, path: str, field: str, current: dict[str, str]) -> list[str]:
    operation = find(module, method, path)
    item = next(f for f in operation.fields if f.name == field)
    suggester = Suggester(fake(), {("chunking", "experiments"): ["e9"]})
    assert suggester.supports(operation, item)
    return [s.value for s in suggester.values(operation, item, current).items]


def test_node_ids_of_the_label_chosen(operations: Catalog, find: Find) -> None:
    assert values(find, "data", "GET", "/nodes/{label}/{id}", "id", {"label": "PIAA"}) == ["120501"]
    assert values(find, "data", "GET", "/nodes/{label}/{id}", "id", {}) == []  # no label yet


def test_experiments_with_the_recent_ones_first_and_their_scores(operations: Catalog, find: Find) -> None:
    assert values(find, "chunking", "GET", "/experiments/{id}", "id", {}) == ["e9", "e1"]
    path = "/experiments/{id}/scores/{score_id}"
    assert values(find, "chunking", "GET", path, "score_id", {"id": "e1"}) == ["s1"]


def test_ingesta_years_and_body_fields_of_chunking(operations: Catalog, find: Find) -> None:
    assert values(find, "ingesta", "GET", "/stats/years/{year}", "year", {}) == ["2024"]
    assert values(find, "chunking", "POST", "/runs", "sha256s", {}) == ["abc"]


def test_pipeline_stages_with_the_current_one_first(operations: Catalog, find: Find) -> None:
    path = "/runs/{id}/stages/{stage}/decision"
    assert values(find, "pipeline", "POST", path, "stage", {"id": "p1"}) == ["chunking", "conversion"]


def test_choices_and_booleans_need_no_list(operations: Catalog, find: Find) -> None:
    operation = find("data", "GET", "/nodes/{label}")
    label = operation.fields[0]
    assert not Suggester(fake(), {}).supports(operation, label)


FILES: list[JsonValue] = [
    {"tipo": "pdf", "anio": 2024, "mes_num": 3, "semana": "Semana_01", "codigo": "A"},
    {"tipo": "pdf", "anio": 2025, "mes_num": 3, "semana": "Semana_02", "codigo": "B"},
    {"tipo": "docx", "anio": 2025, "mes_num": 4, "semana": "Semana_02", "codigo": "C"},
    {"tipo": "doc", "anio": 2025, "mes_num": 4, "semana": "Semana_03", "codigo": "C"},
]


def corpus(asked: list[str]) -> ApiClient:
    """GET /ingesta/data over FILES, filtering like ingesta does, one file per page (to follow every page)."""

    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url.query))
        query = request.url.params
        rows = [
            row
            for row in FILES
            if isinstance(row, dict)
            and (not query.get_list("type") or row["tipo"] in query.get_list("type"))
            and (not query.get("year") or str(row["anio"]) == query.get("year"))
            and (not query.get("code") or row["codigo"] == query.get("code"))
        ]
        page = int(query.get("page", "1"))
        return httpx.Response(200, json={"archivos": rows[page - 1 : page], "paginas": len(rows)})

    return ApiClient(httpx.Client(transport=httpx.MockTransport(answer), base_url="http://test"))


def facet(find: Find, path: str, field: str, current: dict[str, str], asked: list[str]) -> list[tuple[str, str]]:
    module = "ingesta" if path == "/data" else "chunking"
    operation = find(module, "GET" if path == "/data" else "POST", path)
    item = next(f for f in operation.fields if f.name == field)
    found = Suggester(corpus(asked), {}).values(operation, item, current)
    assert found.source.startswith("GET /ingesta/data")
    return [(s.value, s.detail) for s in found.items]


def test_filters_only_offer_values_that_still_give_files(find: Find) -> None:
    asked: list[str] = []
    assert facet(find, "/data", "year", {}, asked) == [("2024", "1 archivos"), ("2025", "3 archivos")]
    assert len(asked) == 4  # every page was read
    assert facet(find, "/data", "type", {"year": "2025"}, asked) == [
        ("doc", "1 archivos"), ("docx", "1 archivos"), ("pdf", "1 archivos")
    ]  # fmt: skip
    assert facet(find, "/data", "year", {"type": "docx, doc", "year": "2024"}, asked) == [("2025", "2 archivos")]
    assert facet(find, "/data", "month", {"code": "C"}, asked) == [("4", "abril · 2 archivos")]


def test_the_files_of_a_run_and_of_an_experiment_are_faceted_too(find: Find) -> None:
    assert facet(find, "/runs", "types", {"year": "2024"}, []) == [("pdf", "1 archivos")]
    experiment = facet(find, "/experiments", "files.code", {"files.types": "pdf"}, [])
    assert experiment == [("A", "1 archivos"), ("B", "1 archivos")]
