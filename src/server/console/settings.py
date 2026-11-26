"""What the console needs to know: where the server is (or how to start it) and where Neo4j and Ollama are (or how to
start them: the Docker Compose project of docker/compose.yaml, feature 054)."""

from dataclasses import dataclass, field
from urllib.parse import urlsplit

NEO4J_CONTAINER = "prueba-chunking-neo4j"
NEO4J_IMAGE = "neo4j:2026.07.1"
NEO4J_VOLUME = "prueba-chunking-neo4j-data"
NEO4J_HTTP_PORT = 7474  # Neo4j Browser, published with the bolt port
BOLT_PORT = 7687
OLLAMA_URL = "http://127.0.0.1:11434"  # OLLAMA_URL in the environment changes it
OLLAMA_PORT = 11434
GPUS = ("amd", "nvidia", "cpu")  # Ollama's variant: docker/compose.<gpu>.yaml over docker/compose.yaml
GPU = "amd"  # the user's GPU (ROCm); --gpu or OLLAMA_GPU change it
COMPOSE_PROJECT = "prueba-chunking"
COMPOSE_DIR = "docker"  # relative to the project root: compose.yaml and one compose.<gpu>.yaml per GPU
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
SERVER_LOG = ".cache/console-server.log"  # relative to the project root


@dataclass(frozen=True)
class ConsoleSettings:
    url: str  # the single server: http://127.0.0.1:8000
    neo4j_url: str
    neo4j_user: str
    neo4j_database: str
    neo4j_password: str | None = field(default=None, repr=False)
    docker: bool = True  # start Neo4j and Ollama with Docker when they don't answer and are local
    serve_options: tuple[str, ...] = ()  # passed as they are to `serve` (--base, --ingest, --memory, --db)
    container: str = NEO4J_CONTAINER
    image: str = NEO4J_IMAGE
    volume: str = NEO4J_VOLUME
    ollama_url: str = OLLAMA_URL
    gpu: str = GPU
    keep_docker: bool = False  # leave running, on exit, what the console started
    compose_project: str = COMPOSE_PROJECT

    @property
    def server_address(self) -> tuple[str, int]:
        parts = urlsplit(self.url)
        return parts.hostname or "127.0.0.1", parts.port or 80

    @property
    def bolt_address(self) -> tuple[str, int]:
        parts = urlsplit(self.neo4j_url)
        return parts.hostname or "localhost", parts.port or BOLT_PORT

    @property
    def ollama_address(self) -> tuple[str, int]:
        parts = urlsplit(self.ollama_url)
        return parts.hostname or "127.0.0.1", parts.port or OLLAMA_PORT

    @staticmethod
    def is_local(host: str) -> bool:
        return host in LOCAL_HOSTS
