"""Settings of the parsing module: the fixed configuration (docling.py) and the technical values (settings.py)."""

from common.config import DATA_PATH, HTTP_TIMEOUT, MAX_PER_PAGE, PARSING_PATH, PER_PAGE

from .docling import PARSING, PARSING_VERSION, ParsingConfig
from .settings import (
    MAX_WAITING,
    PREVIEW_MAX_BYTES,
    PREVIEW_MAX_PAGES,
    PREVIEW_TIMEOUT,
    PREVIEW_TYPES,
    RAW_PAGE,
    RUN_TIMEOUT,
    UNASSIGNED_CODE,
)

__all__ = [
    "DATA_PATH",
    "HTTP_TIMEOUT",
    "MAX_PER_PAGE",
    "MAX_WAITING",
    "PARSING",
    "PARSING_PATH",
    "PARSING_VERSION",
    "PER_PAGE",
    "PREVIEW_MAX_BYTES",
    "PREVIEW_MAX_PAGES",
    "PREVIEW_TIMEOUT",
    "PREVIEW_TYPES",
    "RAW_PAGE",
    "RUN_TIMEOUT",
    "UNASSIGNED_CODE",
    "ParsingConfig",
]
