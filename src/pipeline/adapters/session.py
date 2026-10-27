"""HttpModules: one httpx.Client against the same server (self_url) for the whole app, shared by the clients of
ingesta, chunking and data and by the store (httpx.Client is safe between threads)."""

import httpx

from pipeline.config import CHUNKING_PATH, DATA_PATH, INGESTA_PATH, RUN_TIMEOUT
from pipeline.models import Modules

from .chunking_client import ChunkingClient
from .data_client import DataClient
from .ingesta_client import IngestaClient
from .run_store import GraphRunStore


class HttpModules:
    def __init__(
        self,
        base_url: str,
        ingesta_path: str = INGESTA_PATH,
        chunking_path: str = CHUNKING_PATH,
        data_path: str = DATA_PATH,
        timeout: float = RUN_TIMEOUT,
    ) -> None:
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)
        self.modules = Modules(
            IngestaClient(self._client, ingesta_path),
            ChunkingClient(self._client, chunking_path),
            DataClient(self._client, data_path),
        )
        self.store = GraphRunStore(self._client, data_path)

    def close(self) -> None:
        self._client.close()
