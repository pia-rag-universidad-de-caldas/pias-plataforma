"""Autocomplete (feature 035): each field reads its values from what exists, over HTTP; recent ids first. Against a
fake server (httpx.MockTransport) that answers what each module would."""

import json
from collections.abc import Callable

import httpx

from server.console.bodies import JsonValue
from server.console.catalog import Field, Module, Operation
from server.console.client import ApiClient
from server.console.suggestions import Suggester

type Catalog = dict[str, tuple[Operation, ...]]
type Find = Callable[[str, str, str], Operation]

ANSWERS: dict[str, JsonValue] = {
    "/data/nodes/PIAA": {"nodes": [{"label": "PIAA", "id": "120501", "properties": {"nombre": "Cálculo I"}}]},
    "/chunking/experiments": [{"id": "e1", "name": "prueba", "status": "finished", "created": "2026"}],
    "/chunking/runs": [{"id": "r1", "status": "partial", "requested": "2026"}],
    "/data/nodes/JSON": {"nodes": [{"label": "JSON", "id": "abc", "properties": {"estado": "parseado"}}]},
    "/ingesta/stats/years": {"filas_anios": [{"anio": 2024, "archivos": 10}]},
    "/ingesta/data": {
        "archivos": [{"origen": "2024/x.pdf", "sha256": "abc", "codigo": "120501", "nombre": "x.pdf"}],
        "paginas": 1,
    },
    "/llm/models": {"admitted": [{"name": "qwen2.5:0.5b", "installed": True, "vision": False, "default": False}]},
    "/llm/models/pulls": [{"id": "pull1", "model": "qwen2.5:0.5b", "status": "finished"}],
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


def test_experiments_with_the_recent_ones_first_and_chunking_runs(operations: Catalog, find: Find) -> None:
    assert values(find, "chunking", "GET", "/experiments/{id}", "id", {}) == ["e9", "e1"]
    assert values(find, "chunking", "POST", "/experiments/{id}/resume", "id", {}) == ["e9", "e1"]
    assert values(find, "chunking", "GET", "/runs/{id}", "id", {}) == ["r1"]
    assert values(find, "chunking", "POST", "/runs/{id}/resume", "id", {}) == ["r1"]


def test_ingesta_years_and_body_fields_of_chunking(operations: Catalog, find: Find) -> None:
    assert values(find, "ingesta", "GET", "/stats/years/{year}", "year", {}) == ["2024"]
    assert values(find, "chunking", "POST", "/experiments", "sha256s", {}) == ["abc"]  # the parsed ones, from data
    assert values(find, "ingesta", "GET", "/data/file", "sha256", {}) == ["abc"]


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
    operation = find("ingesta", "GET", path)
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


def test_llm_models_and_pulls(find: Find) -> None:
    assert values(find, "llm", "PUT", "/config", "model", {}) == ["qwen2.5:0.5b"]
    assert values(find, "llm", "POST", "/models/pull", "name", {}) == ["qwen2.5:0.5b"]
    assert values(find, "llm", "GET", "/models/pulls/{id}", "id", {}) == ["pull1"]


# Feature 057: a run's sha256s offer only what is still missing in its stage.

PROGRESS: dict[str, JsonValue] = {
    "/parsing/config": {"fingerprint": "fp-parse"},
    "/chunking/config": {"fingerprint": "fp-chunk"},
    "/embeddings/config": {"model": "minilm", "vector_property": "embedding_minilm_384"},
    "/embeddings/models": [{"name": "e5", "vector_property": "embedding_e5_768"}],
}


def missing_ones(find: Find, module: str, current: dict[str, str]) -> tuple[list[str], list[str]]:
    """The sha256s offered for POST /<module>/runs and the queries sent to data's progress."""
    asked: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/data/progress/"):
            asked.append(f"{request.url.path}?{request.url.query.decode()}")
            return httpx.Response(200, json={"missing": 2, "sha256s": ["m1", "m2"]})
        found = PROGRESS.get(request.url.path)
        return httpx.Response(200, json=found) if found is not None else httpx.Response(404, json={})

    client = ApiClient(httpx.Client(transport=httpx.MockTransport(answer), base_url="http://test"))
    operation = find(module, "POST", "/runs")
    item = next(f for f in operation.fields if f.name == "sha256s")
    return [s.value for s in Suggester(client, {}).values(operation, item, current).items], asked


def test_a_parsing_run_offers_what_is_not_parsed(operations: Catalog, find: Find) -> None:
    found, [query] = missing_ones(find, "parsing", {})
    assert found == ["m1", "m2"] and query.startswith("/data/progress/parsing?list=missing")
    assert "fingerprint=fp-parse" in query


def test_a_chunking_run_offers_what_is_not_chunked_with_the_active_configuration(
    operations: Catalog, find: Find
) -> None:
    found, [query] = missing_ones(find, "chunking", {})
    assert found == ["m1", "m2"] and "/data/progress/chunking?" in query and "fingerprint=fp-chunk" in query


def test_an_embeddings_run_offers_what_its_model_has_not_embedded(operations: Catalog, find: Find) -> None:
    _, [active] = missing_ones(find, "embeddings", {})
    _, [other] = missing_ones(find, "embeddings", {"model": "e5"})
    assert "property=embedding_minilm_384" in active and "property=embedding_e5_768" in other


# feature 062: only what is missing, read from data


def scripted(answers: dict[str, JsonValue], asked: list[str]) -> ApiClient:
    def answer(request: httpx.Request) -> httpx.Response:
        asked.append(f"{request.method} {request.url.path}")
        found = answers.get(request.url.path)
        return httpx.Response(200, json=found) if found is not None else httpx.Response(404, json={})

    return ApiClient(httpx.Client(transport=httpx.MockTransport(answer), base_url="http://test"))


def offered(client: ApiClient, operation: Operation, field: str, current: dict[str, str]) -> tuple[list[str], str]:
    item = next(f for f in operation.fields if f.name == field)
    found = Suggester(client, {}).values(operation, item, current)
    return [s.value for s in found.items], found.source


def by_hand(module: str, path: str) -> Operation:
    """A route another part of feature 062 adds: its fields as its spec says."""
    fields = (Field("id", "path", "text", required=True), Field("sha256s", "body", "text", repeated=True))
    return Operation(Module(module, f"/{module}"), "POST", path, "", "", fields, {})


SELECTED: dict[str, JsonValue] = {"/data/documents/select": {"total": 7, "sha256s": ["n1", "n2"], "pages": 1}}
EXPERIMENT_DOCUMENTS: dict[str, JsonValue] = {
    "/data/nodes/EXPERIMENTO/e1/relationships": [
        {"type": "EXP_TIENE_DOCUMENTO", "source": {"label": "EXPERIMENTO", "id": "e1"},
         "target": {"label": "EXP_DOCUMENTO", "id": "e1:d1"}},
        {"type": "EXP_TIENE_DOCUMENTO", "source": {"label": "EXPERIMENTO", "id": "e1"},
         "target": {"label": "EXP_DOCUMENTO", "id": "e1:d2"}},
    ],
}  # fmt: skip
DOCUMENTS = ("/experiments/{id}/documents", "/experiments/{id}/resume")


def test_adding_to_an_experiment_offers_the_parsed_ones_it_doesnt_have() -> None:
    asked: list[str] = []
    operation = by_hand("chunking", DOCUMENTS[0])
    found, source = offered(scripted(SELECTED, asked), operation, "sha256s", {"id": "e1"})
    assert found == ["n1", "n2"] and asked == ["POST /data/documents/select"]
    assert source.startswith("POST /data/documents/select (universe parsed sin los de e1): faltan 7")


def test_without_the_selection_route_the_experiment_documents_are_read_from_data() -> None:
    parsed: dict[str, JsonValue] = {
        "/data/nodes/JSON": {"nodes": [{"id": "d1", "properties": {}}, {"id": "d3", "properties": {}}]},
        **EXPERIMENT_DOCUMENTS,
    }
    found, source = offered(scripted(parsed, []), by_hand("chunking", DOCUMENTS[0]), "sha256s", {"id": "e1"})
    assert found == ["d3"] and "faltan 1" in source


def test_resuming_an_embeddings_experiment_offers_its_documents_without_a_vector() -> None:
    detail = json.dumps({"chunking_experiment": "e1", "embedded": ["d1"]})
    answers: dict[str, JsonValue] = {
        "/data/nodes/EXP_EMBEDDINGS/x1": {"id": "x1", "properties": {"detalle": detail}},
        **EXPERIMENT_DOCUMENTS,
    }
    found, source = offered(scripted(answers, []), by_hand("embeddings", DOCUMENTS[1]), "sha256s", {"id": "x1"})
    assert found == ["d2"] and "faltan 1 de 2" in source


def test_a_pipeline_that_extends_an_experiment_offers_what_it_lacks(find: Find) -> None:
    asked: list[str] = []
    values = {"template": "experimentos", "params.chunkear.extend": "e1"}
    found, _ = offered(scripted(SELECTED, asked), find("pipeline", "POST", "/runs"), "files.sha256s", values)
    assert found == ["n1", "n2"] and asked == ["POST /data/documents/select"]


def test_a_pipeline_over_the_official_chunks_offers_what_the_first_model_lacks(find: Find) -> None:
    answers: dict[str, JsonValue] = {
        "/embeddings/models": [{"name": "e5", "vector_property": "embedding_e5_768"}],
        "/data/progress/embeddings": {"missing": 3, "sha256s": ["m1"]},
    }
    values = {"template": "experimentos", "params.chunkear.official": "true", "params.embeber.models": "e5, bge"}
    found, source = offered(scripted(answers, []), find("pipeline", "POST", "/runs"), "files.sha256s", values)
    assert found == ["m1"] and "3 sin vectores de e5" in source


def test_a_new_experiment_in_a_pipeline_offers_the_parsed_documents(find: Find) -> None:
    found, source = offered(scripted(SELECTED, []), find("pipeline", "POST", "/runs"), "files.sha256s",
                            {"template": "experimentos"})  # fmt: skip
    assert found == ["n1", "n2"] and "faltan 7" in source


def test_a_production_pipeline_offers_ingesta_chunkable_files(find: Find) -> None:
    found, _ = offered(fake(), find("pipeline", "POST", "/runs"), "files.sha256s", {})
    assert found == ["abc"]


def test_the_models_of_a_pipeline_say_their_dimension_and_budget(find: Find) -> None:
    answers: dict[str, JsonValue] = {
        "/embeddings/models": [{"name": "bge", "dimensions": 1024, "max_tokens": 8192, "default_passage_budget": 510}]
    }
    run = find("pipeline", "POST", "/runs")
    item = next(f for f in run.fields if f.name == "params.embeber.models")
    [model] = Suggester(scripted(answers, []), {}).values(run, item, {}).items
    assert model.detail == "1024 dim · hasta 8192 tokens · chunk de hasta 510"
