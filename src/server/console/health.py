"""Which services are active, asked again at every step of the navigation (feature 039), and which operations can't
work without them: their buttons are blocked, with the reason."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from .bodies import JsonValue
from .catalog import Operation

SERVER, INGESTA, NEO4J, CHUNKING, DOCLING, PIPELINE = "servidor", "ingesta", "neo4j", "chunking", "docling", "pipeline"
VECTORS = "vectores"  # torch and transformers, for embeddings (feature 046)
OLLAMA = "ollama"  # the language models, for llm (feature 047)

# What works without the service: everything else in the module needs it.
_NO_GRAPH = {
    "data": ("/schema", "/health"),
    "parsing": ("/health", "/processes", "/config", "/runs"),
    "chunking": ("/health", "/processes"),
    "embeddings": ("/health", "/processes", "/models"),
    "llm": ("/health", "/processes", "/models"),  # the rest reads the active configuration in data
    "pipeline": ("/health", "/processes", "/actions", "/actors"),
    "consultas": ("/health",),
}
_NO_MEMORY = ("/health", "/processes", "/source", "/runs")
# What the console can't send (feature 049: a multipart body with files): the API or the front does it.
_API_ONLY = {
    ("ingesta", "POST", "/uploads"): "subir archivos es desde la API o el front (multipart): http/ingesta/uploads.http"
}
# What chunks with docling-core (feature 043).
_CHUNKS = frozenset({"/experiments", "/runs"})
# What runs an embedding model (feature 046).
_EMBEDS = frozenset({"/runs", "/experiments", "/vectors"})
# What asks Ollama for something (feature 047); GET /models too, but it says why it can't (503).
_OLLAMA = frozenset({("POST", "/chat"), ("POST", "/models/pull"), ("DELETE", "/models/{name}")})
# What turns a question into a vector (feature 048).
_ASKS = frozenset({"/search", "/ask", "/compare"})


class _Reader(Protocol):
    def get_json(self, path: str, params: dict[str, str]) -> JsonValue: ...


@dataclass(frozen=True)
class Service:
    name: str
    active: bool
    detail: str = ""  # why it isn't


@dataclass(frozen=True)
class Health:
    services: tuple[Service, ...]

    def active(self, name: str) -> bool:
        return any(s.name == name and s.active for s in self.services)

    def detail(self, name: str) -> str:
        return next((s.detail for s in self.services if s.name == name), "")

    @property
    def line(self) -> str:
        return " ".join(f"{'●' if s.active else '✗'} {s.name}" for s in self.services)


def _state(modules: JsonValue, name: str) -> tuple[bool, str]:
    found = modules.get(name) if isinstance(modules, dict) else None
    if not isinstance(found, dict):
        return False, "no respondió"
    return found.get("status") == "ok", str(found.get("detail") or "")


def read_health(client: _Reader) -> Health:
    """The state of every service now."""
    server = client.get_json("/health", {})
    if not isinstance(server, dict):
        names = (SERVER, INGESTA, NEO4J, CHUNKING, DOCLING, VECTORS, OLLAMA, PIPELINE)
        return Health(tuple(Service(name, False, "el servidor no responde") for name in names))
    modules = server.get("modules")
    ingesta, ingesta_detail = _state(modules, "ingesta")
    neo4j, neo4j_detail = _state(modules, "data")
    chunking = client.get_json("/chunking/health", {})
    docling = isinstance(chunking, dict) and chunking.get("docling_core") == "installed"
    embeddings = client.get_json("/embeddings/health", {})
    vectors = isinstance(embeddings, dict) and embeddings.get("models") == "installed"
    llm = client.get_json("/llm/health", {})
    ollama = isinstance(llm, dict) and llm.get("ollama") == "ok"
    where = llm.get("ollama_url") if isinstance(llm, dict) else None
    pipeline = client.get_json("/pipeline/health", {})
    return Health(
        (
            Service(SERVER, True),
            Service(INGESTA, ingesta, ingesta_detail),
            Service(NEO4J, neo4j, neo4j_detail),
            Service(CHUNKING, isinstance(chunking, dict), "no respondió"),
            Service(DOCLING, docling, "docling-core no está instalado: uv sync --extra chunk"),
            Service(VECTORS, vectors, "torch y transformers no están instalados: uv sync --extra embed"),
            Service(OLLAMA, ollama, f"Ollama no responde en {where or 'su URL'}: ollama serve o --ollama-url"),
            Service(PIPELINE, isinstance(pipeline, dict), "no respondió"),
        )
    )


def _under(path: str, allowed: Sequence[str]) -> bool:
    return any(path == root or path.startswith(f"{root}/") for root in allowed)


def blocked(operation: Operation, health: Health) -> str:
    """Why this operation can't work now; "" if it can."""
    module, path = operation.module.name, operation.path
    if not health.active(SERVER):
        return "el servidor no responde"
    if reason := _API_ONLY.get((module, operation.method, path)):
        return reason
    if module in _NO_GRAPH and not health.active(NEO4J) and not _under(path, _NO_GRAPH[module]):
        return "Neo4j está desactivado"
    if module == INGESTA and not health.active(INGESTA) and not _under(path, _NO_MEMORY):
        return "ingesta no tiene memoria: lanza primero una ingesta (corridas)"
    if module == "parsing" and operation.method == "POST" and path == "/runs" and not health.active(NEO4J):
        return "Neo4j está desactivado: los archivos se leen de data"
    if module == CHUNKING and operation.method == "POST" and path in _CHUNKS:
        if not health.active(DOCLING):
            return "docling-core no está instalado: uv sync --extra chunk"
        if not health.active(NEO4J):
            return "Neo4j está desactivado"
    if module == "embeddings" and operation.method == "POST" and path in _EMBEDS and not health.active(VECTORS):
        return "torch y transformers no están instalados: uv sync --extra embed"
    if module == "llm" and (operation.method, path) in _OLLAMA and not health.active(OLLAMA):
        return health.detail(OLLAMA) or "Ollama no responde"
    if module == "consultas" and operation.method == "POST" and path in _ASKS and not health.active(VECTORS):
        return "torch y transformers no están instalados: la pregunta no se puede convertir en vector"
    if (
        module == "consultas"
        and operation.method == "POST"
        and path in ("/ask", "/compare")
        and not health.active(OLLAMA)
    ):
        return health.detail(OLLAMA) or "Ollama no responde: no hay quién redacte la respuesta"
    return ""


def all_blocked(operations: Sequence[Operation], health: Health) -> str:
    """The reason if every one of them is blocked; "" if any can be used."""
    reasons = [blocked(operation, health) for operation in operations]
    return reasons[0] if reasons and all(reasons) else ""
