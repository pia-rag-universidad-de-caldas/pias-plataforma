"""Adapters of parsing: the only place that uses docling, docling_core and httpx (Ruff TID251). Docling turns a file
into a DoclingDocument; data, over HTTP, has the RAW it reads, the JSON it writes and the record of its runs."""

from .data_client import DATA_ERRORS, DataClient, batch_body
from .docling_parser import DoclingParser, is_infrastructure, joined, text_pages
from .mappers import raw_file, raw_state, stored_parse
from .roman_titles import promote_roman_titles, roman_level
from .session import HttpSession
from .stores import GraphRunStore, HttpParsedSink, HttpRawSource

__all__ = [
    "DATA_ERRORS",
    "DataClient",
    "DoclingParser",
    "GraphRunStore",
    "HttpParsedSink",
    "HttpRawSource",
    "HttpSession",
    "batch_body",
    "is_infrastructure",
    "joined",
    "promote_roman_titles",
    "raw_file",
    "raw_state",
    "roman_level",
    "stored_parse",
    "text_pages",
]
