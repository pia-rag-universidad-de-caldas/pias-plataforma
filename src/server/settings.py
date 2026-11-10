"""Settings of the single server: those of each module plus how they reach each other."""

from dataclasses import dataclass, field
from urllib.parse import urlsplit

from data.api import ApiSettings as DataSettings
from ingesta.api import ApiSettings as IngestaSettings
from llm.config import OLLAMA_URL

LOCAL_HOST = "127.0.0.1"
ALL_INTERFACES = frozenset({"", "0.0.0.0", "::"})  # listening on these, the modules call each other on LOCAL_HOST
LOCAL_NAMES = frozenset({"localhost", LOCAL_HOST, "::1"})  # always answered: what the machine itself uses
# The largest body is a document's POST /data/batch. The document with the most text of the corpus has 147 000
# characters; with every copy it stores and JSON's worst escaping that is under 3 MiB, so this leaves more than 10×.
MAX_BODY_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class ServerSettings:
    ingesta: IngestaSettings
    data: DataSettings
    self_url: str  # base URL with which the modules call each other over HTTP (feature 022)
    neo4j_password: str | None = field(default=None, repr=False)  # None: data is mounted as unavailable
    allowed_hosts: tuple[str, ...] = ()  # names it also answers to, besides LOCAL_NAMES and the host of self_url
    max_body_bytes: int = MAX_BODY_BYTES
    ollama_url: str = OLLAMA_URL  # where llm finds Ollama (feature 047): --ollama-url, else OLLAMA_URL

    @property
    def trusted_hosts(self) -> frozenset[str]:
        own = urlsplit(self.self_url).hostname
        return LOCAL_NAMES | set(self.allowed_hosts) | ({own} if own else set())

    @staticmethod
    def url_for(host: str, port: int) -> str:
        """self_url for a server listening on host:port."""
        return f"http://{LOCAL_HOST if host in ALL_INTERFACES else host}:{port}"
