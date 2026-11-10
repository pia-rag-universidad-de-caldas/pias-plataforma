"""One HTTP session per request or job (feature 022): a single httpx.Client against the same server (self_url), shared
by the stores in data. Chunking talks only to data (feature 043). Every httpx error becomes the port's error: the
domain never sees httpx."""

from types import TracebackType
from typing import Self

import httpx

from chunking.config import DATA_PATH, RUN_TIMEOUT

from .data import GraphConfigStore, GraphDocumentStore, GraphExperimentStore, GraphRunStore


class HttpSession:
    """`with HttpSession(self_url) as session:` → session.documents, .experiments, .config and .runs."""

    def __init__(self, base_url: str, data_path: str = DATA_PATH, timeout: float = RUN_TIMEOUT) -> None:
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)
        self.documents = GraphDocumentStore(self._client, data_path)
        self.experiments = GraphExperimentStore(self._client, data_path)
        self.config = GraphConfigStore(self._client, data_path)
        self.runs = GraphRunStore(self._client, data_path)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, kind: type[BaseException] | None, error: BaseException | None, traceback: TracebackType | None
    ) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()
