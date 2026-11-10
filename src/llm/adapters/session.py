"""One HTTP session to data per request: a single httpx.Client against the same server (self_url). Every httpx error
becomes the port's error: the domain never sees httpx."""

from types import TracebackType
from typing import Self

import httpx

from llm.config import DATA_PATH, DATA_TIMEOUT

from .data import DataClient, GraphConfigStore


class HttpSession:
    """`with HttpSession(self_url) as session:` → session.config."""

    def __init__(
        self,
        base_url: str,
        data_path: str = DATA_PATH,
        timeout: float = DATA_TIMEOUT,
        transport: httpx.BaseTransport | None = None,  # tests: an httpx.MockTransport
    ) -> None:
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout, transport=transport)
        self.config = GraphConfigStore(DataClient(self._client, data_path))

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, kind: type[BaseException] | None, error: BaseException | None, traceback: TracebackType | None
    ) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()
