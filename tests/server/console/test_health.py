"""The services, asked at each step (feature 039): what each one being down blocks, and what it doesn't."""

from collections.abc import Callable

from server.console.bodies import JsonValue
from server.console.catalog import Operation
from server.console.health import (
    CHUNKING,
    DOCLING,
    INGESTA,
    NEO4J,
    OLLAMA,
    PIPELINE,
    SERVER,
    VECTORS,
    Health,
    Service,
    blocked,
    read_health,
)

type Find = Callable[[str, str, str], Operation]


def health(*down: str) -> Health:
    names = (SERVER, INGESTA, NEO4J, CHUNKING, DOCLING, VECTORS, OLLAMA, PIPELINE)
    return Health(tuple(Service(name, name not in down) for name in names))


def test_without_neo4j_only_what_does_not_touch_the_graph_is_usable(find: Find) -> None:
    down = health(NEO4J)
    assert "Neo4j" in blocked(find("data", "GET", "/nodes/{label}"), down)
    assert blocked(find("data", "GET", "/schema"), down) == ""
    assert "Neo4j" in blocked(find("chunking", "POST", "/runs"), down)
    assert blocked(find("chunking", "GET", "/processes"), down) == ""
    assert "Neo4j" in blocked(find("pipeline", "GET", "/pipelines"), down)
    assert blocked(find("pipeline", "GET", "/actions"), down) == ""


def test_without_memory_an_ingestion_can_still_be_launched_to_create_it(find: Find) -> None:
    down = health(INGESTA)
    assert "memoria" in blocked(find("ingesta", "GET", "/data"), down)
    assert blocked(find("ingesta", "POST", "/runs"), down) == ""
    assert blocked(find("ingesta", "GET", "/source"), down) == ""


def test_without_docling_only_what_chunks_is_blocked(find: Find) -> None:
    down = health(DOCLING)
    assert "docling-core" in blocked(find("chunking", "POST", "/runs"), down)
    assert "docling-core" in blocked(find("chunking", "POST", "/experiments"), down)
    assert blocked(find("chunking", "PUT", "/config"), down) == ""
    assert blocked(find("chunking", "GET", "/experiments"), down) == ""


def test_without_torch_only_what_embeds_is_blocked(find: Find) -> None:
    down = health(VECTORS)
    assert "torch" in blocked(find("embeddings", "POST", "/runs"), down)
    assert "torch" in blocked(find("embeddings", "POST", "/vectors"), down)
    assert "torch" in blocked(find("consultas", "POST", "/ask"), down)
    assert blocked(find("consultas", "GET", "/chats"), down) == ""
    assert blocked(find("embeddings", "PUT", "/config"), down) == ""
    assert blocked(find("embeddings", "GET", "/models"), down) == ""


def test_without_ollama_only_what_asks_it_is_blocked(find: Find) -> None:
    down = health(OLLAMA)
    assert blocked(find("llm", "POST", "/chat"), down) != ""
    assert blocked(find("llm", "POST", "/models/pull"), down) != ""
    assert blocked(find("llm", "DELETE", "/models/{name}"), down) != ""
    assert blocked(find("llm", "PUT", "/config"), down) == ""
    assert blocked(find("llm", "GET", "/models"), down) == ""
    assert "Neo4j" in blocked(find("llm", "GET", "/config"), health(NEO4J))


def test_with_everything_up_only_what_the_console_cant_send_is_blocked(
    operations: dict[str, tuple[Operation, ...]],
) -> None:
    every = [o for found in operations.values() for o in found]
    refused = {(o.module.name, o.method, o.path) for o in every if blocked(o, health())}
    assert refused == {("ingesta", "POST", "/uploads")}


def test_an_upload_points_to_the_api_and_its_list_is_usable(find: Find) -> None:
    assert "API" in blocked(find("ingesta", "POST", "/uploads"), health())
    assert blocked(find("ingesta", "GET", "/uploads"), health()) == ""


def test_read_health_says_each_service_and_a_dead_server_turns_all_off() -> None:
    answers: dict[str, JsonValue] = {
        "/health": {"modules": {"ingesta": {"status": "ok"}, "data": {"status": "unavailable", "detail": "no bolt"}}},
        "/chunking/health": {"docling_core": "missing"},
        "/embeddings/health": {"models": "installed"},
        "/llm/health": {"ollama": "unavailable", "ollama_url": "http://127.0.0.1:11434"},
        "/pipeline/health": {"status": "degraded"},
    }

    class Client:
        def __init__(self, found: dict[str, JsonValue]) -> None:
            self.found = found

        def get_json(self, path: str, params: dict[str, str]) -> JsonValue:
            return self.found.get(path)

    seen = read_health(Client(answers))
    assert seen.active(SERVER) and seen.active(INGESTA) and seen.active(CHUNKING) and seen.active(PIPELINE)
    assert not seen.active(NEO4J) and seen.detail(NEO4J) == "no bolt" and not seen.active(DOCLING)
    assert seen.active(VECTORS) and not seen.active(OLLAMA) and "11434" in seen.detail(OLLAMA)
    assert seen.line.startswith("● servidor ● ingesta ✗ neo4j")
    assert not any(s.active for s in read_health(Client({})).services)


def test_without_ollama_a_question_can_be_searched_but_not_answered(find: Find) -> None:
    down = health(OLLAMA)
    assert "Ollama" in blocked(find("consultas", "POST", "/ask"), down)
    assert blocked(find("consultas", "POST", "/search"), down) == ""
