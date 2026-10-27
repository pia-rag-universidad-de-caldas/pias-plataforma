"""What the console needs to know: where the server is (or how to start it) and where Neo4j is (or how to start it)."""

from dataclasses import dataclass, field
from urllib.parse import urlsplit

NEO4J_CONTAINER = "prueba-chunking-neo4j"
NEO4J_IMAGE = "neo4j:2026.07.1"
NEO4J_VOLUME = "prueba-chunking-neo4j-data"
NEO4J_HTTP_PORT = 7474  # Neo4j Browser, published with the bolt port
BOLT_PORT = 7687
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
SERVER_LOG = ".cache/console-server.log"  # relative to the project root


@dataclass(frozen=True)
class ConsoleSettings:
    url: str  # the single server: http://127.0.0.1:8000
    neo4j_url: str
    neo4j_user: str
    neo4j_database: str
    neo4j_password: str | None = field(default=None, repr=False)
    docker: bool = True  # start Neo4j with Docker when it doesn't answer and is local
    serve_options: tuple[str, ...] = ()  # passed as they are to `serve` (--base, --ingest, --memory, --db)
    container: str = NEO4J_CONTAINER
    image: str = NEO4J_IMAGE
    volume: str = NEO4J_VOLUME

    @property
    def server_address(self) -> tuple[str, int]:
        parts = urlsplit(self.url)
        return parts.hostname or "127.0.0.1", parts.port or 80

    @property
    def bolt_address(self) -> tuple[str, int]:
        parts = urlsplit(self.neo4j_url)
        return parts.hostname or "localhost", parts.port or BOLT_PORT

    @staticmethod
    def is_local(host: str) -> bool:
        return host in LOCAL_HOSTS
