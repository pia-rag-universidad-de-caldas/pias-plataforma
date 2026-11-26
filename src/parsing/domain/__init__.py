"""Business rules of parsing, without I/O: what is pending, the batch of a parsed document, a run and the text of a
preview."""

from .check import Check
from .codec import decode, encode
from .fingerprint import fingerprint
from .graph import ParsedGraph
from .preview import as_text, preview, sections
from .runner import OnDocument, ParsingRunner

__all__ = [
    "Check",
    "OnDocument",
    "ParsedGraph",
    "ParsingRunner",
    "as_text",
    "decode",
    "encode",
    "fingerprint",
    "preview",
    "sections",
]
