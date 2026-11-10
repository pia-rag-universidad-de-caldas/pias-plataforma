"""One HTTP session per request or job: a single httpx.Client against the same server (self_url), shared by the ports
over data, the only module embeddings talks to. Every httpx error becomes the port's error: the domain never sees
httpx."""

from types import TracebackType
from typing import Self

import httpx

from embeddings.config import DATA_PATH, RUN_TIMEOUT

from .data import DataClient, GraphConfigStore, GraphRunStore, HttpChunkSource, HttpVectorStore


class HttpSession:
    """`with HttpSession(self_url) as session:` → session.source, .vectors, .config and .runs."""

    def __init__(
        self,
        base_url: str,
        data_path: str = DATA_PATH,
        timeout: float = RUN_TIMEOUT,
        transport: httpx.BaseTransport | None = None,  # tests: an httpx.MockTransport
    ) -> None:
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout, transport=transport)
        data = DataClient(self._client, data_path)
        self.source = HttpChunkSource(data)
        self.vectors = HttpVectorStore(data)
        self.config = GraphConfigStore(data)
        self.runs = GraphRunStore(data)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, kind: type[BaseException] | None, error: BaseException | None, traceback: TracebackType | None
    ) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()
