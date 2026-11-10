"""Route dependencies: the app settings and the resources opened per request.

The memory is opened and closed in each request (as in each CLI command): the SQLConverter keeps the active
connection and is not shared across the threads in which FastAPI serves the synchronous routes.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from common.config import DATA_PATH
from ingesta.adapters import LocalFileAdapter, SQLORMAdapter
from ingesta.config import RAW_LIMIT
from ingesta.models import (
    CategoryRepository,
    FileAdapter,
    FileRepository,
    ORMAdapter,
    RunRepository,
    UploadRepository,
)
from ingesta.repository import DbCategoryRepository, DbFileRepository, DbRunRepository, DbUploadRepository
from ingesta.tables import TABLES


@dataclass(frozen=True)
class ApiSettings:
    base: str  # absolute input folder (data/base/)
    ingest: str  # absolute output folder (data/ingesta/)
    memory: str  # URL of the memory database
    # Where data is (feature 042): each ingestion publishes the chunkable files there. Without self_url, it doesn't.
    self_url: str | None = None  # base URL of the server that mounts the modules (server sets it)
    data_path: str = DATA_PATH  # prefix of data in that server
    raw_limit: int = RAW_LIMIT  # largest body data accepts (the server's max_body_bytes)


def _settings(request: Request) -> ApiSettings:
    settings: ApiSettings = request.app.state.settings
    return settings


def _memory(settings: Annotated[ApiSettings, Depends(_settings)]) -> Iterator[ORMAdapter]:
    data = SQLORMAdapter.from_existing(settings.memory, TABLES)
    try:
        yield data
    finally:
        data.close()


def _files(memory: Annotated[ORMAdapter, Depends(_memory)]) -> FileRepository:
    return DbFileRepository(memory)


def _categories(memory: Annotated[ORMAdapter, Depends(_memory)]) -> CategoryRepository:
    return DbCategoryRepository(memory)


def _runs(memory: Annotated[ORMAdapter, Depends(_memory)]) -> RunRepository:
    return DbRunRepository(memory)


def _uploads(memory: Annotated[ORMAdapter, Depends(_memory)]) -> UploadRepository:
    return DbUploadRepository(memory)


def _ingest(settings: Annotated[ApiSettings, Depends(_settings)]) -> FileAdapter:
    return LocalFileAdapter(settings.ingest)


# Types for route parameters: `def route(memory: Memory) -> ...`.
Settings = Annotated[ApiSettings, Depends(_settings)]
Memory = Annotated[ORMAdapter, Depends(_memory)]  # existing one; if there is none, MemoryStoreError → 503
# The repositories on that memory (one per request, shared by the dependencies of the same request): routes only
# see the protocols.
Files = Annotated[FileRepository, Depends(_files)]
Categories = Annotated[CategoryRepository, Depends(_categories)]
Runs = Annotated[RunRepository, Depends(_runs)]
Uploaded = Annotated[UploadRepository, Depends(_uploads)]  # the files uploaded through the API (feature 049)
Ingest = Annotated[FileAdapter, Depends(_ingest)]
