"""Settings of the single server: those of each module plus how they reach each other."""

from dataclasses import dataclass, field

from data.api import ApiSettings as DataSettings
from ingesta.api import ApiSettings as IngestaSettings

LOCAL_HOST = "127.0.0.1"
ALL_INTERFACES = frozenset({"", "0.0.0.0", "::"})  # listening on these, the modules call each other on LOCAL_HOST


@dataclass(frozen=True)
class ServerSettings:
    ingesta: IngestaSettings
    data: DataSettings
    self_url: str  # base URL with which the modules call each other over HTTP (feature 022)
    neo4j_password: str | None = field(default=None, repr=False)  # None: data is mounted as unavailable

    @staticmethod
    def url_for(host: str, port: int) -> str:
        """self_url for a server listening on host:port."""
        return f"http://{LOCAL_HOST if host in ALL_INTERFACES else host}:{port}"
