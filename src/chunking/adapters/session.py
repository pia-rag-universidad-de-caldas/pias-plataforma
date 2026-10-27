"""One HTTP session per run (feature 022): a single httpx.Client against the same server (self_url), shared by the
ingesta source and the graph sink. Every httpx error becomes the port's error: the domain never sees httpx."""

from types import TracebackType
from typing import Self

import httpx

from chunking.config import DATA_PATH, INGESTA_PATH, RUN_TIMEOUT

from .data import GraphExperimentStore, GraphHttpSink
from .ingesta import IngestaHttpSource


class HttpSession:
    """`with HttpSession(self_url) as session:` → session.source (ingesta), session.sink (data, production) and
    session.experiments (data, experiments)."""

    def __init__(
        self,
        base_url: str,
        ingesta_path: str = INGESTA_PATH,
        data_path: str = DATA_PATH,
        timeout: float = RUN_TIMEOUT,
    ) -> None:
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout)
        self.source = IngestaHttpSource(self._client, ingesta_path)
        self.sink = GraphHttpSink(self._client, data_path)
        self.experiments = GraphExperimentStore(self._client, data_path)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, kind: type[BaseException] | None, error: BaseException | None, traceback: TracebackType | None
    ) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()
