"""HttpModules: one httpx.Client against the same server (self_url) for the whole app, shared by the clients of
ingesta, parsing, chunking, embeddings, llm and data and by the store (httpx.Client is safe between threads)."""

import httpx

from pipeline.config import CHUNKING_PATH, DATA_PATH, EMBEDDINGS_PATH, INGESTA_PATH, LLM_PATH, PARSING_PATH, RUN_TIMEOUT
from pipeline.models import Modules

from .chunking_client import ChunkingClient
from .data_client import DataClient
from .embeddings_client import EmbeddingsClient
from .ingesta_client import IngestaClient
from .llm_client import LlmClient
from .parsing_client import ParsingClient
from .run_store import GraphRunStore


class HttpModules:
    def __init__(
        self,
        base_url: str,
        ingesta_path: str = INGESTA_PATH,
        chunking_path: str = CHUNKING_PATH,
        data_path: str = DATA_PATH,
        timeout: float = RUN_TIMEOUT,
        parsing_path: str = PARSING_PATH,
        embeddings_path: str = EMBEDDINGS_PATH,
        llm_path: str = LLM_PATH,
    ) -> None:
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)
        self.modules = Modules(
            ingesta=IngestaClient(self._client, ingesta_path),
            parsing=ParsingClient(self._client, parsing_path),
            chunking=ChunkingClient(self._client, chunking_path),
            embeddings=EmbeddingsClient(self._client, embeddings_path),
            data=DataClient(self._client, data_path),
            llm=LlmClient(self._client, llm_path),
        )
        self.store = GraphRunStore(self._client, data_path)

    def close(self) -> None:
        self._client.close()
