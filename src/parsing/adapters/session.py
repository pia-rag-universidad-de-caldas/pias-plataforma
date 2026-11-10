"""HttpSession: one httpx.Client to data (base_url = the server's self_url) and the ports on it."""

from types import TracebackType

import httpx

from parsing.config import RUN_TIMEOUT

from .data_client import DataClient
from .stores import GraphRunStore, HttpParsedSink, HttpRawSource


class HttpSession:
    def __init__(
        self, base_url: str, data_path: str, timeout: float = RUN_TIMEOUT, transport: httpx.BaseTransport | None = None
    ) -> None:
        """`transport`: another way to reach data (a test's MockTransport); None, over the network."""
        self._client = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)
        data = DataClient(self._client, data_path)
        self.raws = HttpRawSource(data)
        self.parsed = HttpParsedSink(data)
        self.runs = GraphRunStore(data)

    def __enter__(self) -> "HttpSession":
        return self

    def __exit__(
        self, kind: type[BaseException] | None, error: BaseException | None, trace: TracebackType | None
    ) -> None:
        self._client.close()
