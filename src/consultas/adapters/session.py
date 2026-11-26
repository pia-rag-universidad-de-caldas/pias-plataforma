"""HttpModules: one httpx.Client against the same server (self_url) for the whole app, shared by the clients of
embeddings, llm, data and parsing (httpx.Client is safe between threads). Every httpx error becomes the
port's error: the domain never sees httpx."""

import httpx

from consultas.config import DATA_PATH, EMBEDDINGS_PATH, LLM_PATH, PARSING_PATH, RUN_TIMEOUT

from .comparison_store import GraphComparisonStore
from .data_client import DataClient
from .embeddings_client import EmbeddingsClient
from .llm_client import LlmClient
from .parsing_client import ParsingClient
from .stores import GraphChatStore, GraphConfigStore


class HttpModules:
    """.vectors (embeddings), .retriever (data's search), .generator and .vision (llm), .chats and .config (data),
    .previewer (parsing: the attached documents); feature 060: .catalog (embeddings' models and experiments),
    .progress (data: the documents with each model's vectors), .chunking (data: the EXPERIMENTO nodes),
    .comparisons (data)."""

    def __init__(
        self,
        base_url: str,
        embeddings_path: str = EMBEDDINGS_PATH,
        llm_path: str = LLM_PATH,
        data_path: str = DATA_PATH,
        timeout: float = RUN_TIMEOUT,
        transport: httpx.BaseTransport | None = None,  # tests: an httpx.MockTransport
        parsing_path: str = PARSING_PATH,
    ) -> None:
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout, transport=transport)
        data = DataClient(self._client, data_path)
        self.vectors = EmbeddingsClient(self._client, embeddings_path)
        self.retriever = data
        self.generator = LlmClient(self._client, llm_path)
        self.vision = self.generator
        self.previewer = ParsingClient(self._client, parsing_path)
        self.chats = GraphChatStore(data)
        self.config = GraphConfigStore(data)
        self.catalog = self.vectors
        self.progress = data
        self.chunking = data
        self.comparisons = GraphComparisonStore(data)

    def close(self) -> None:
        self._client.close()
