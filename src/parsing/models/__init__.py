"""Data classes and interfaces of parsing, one file per function: concepts (in memory), requests, results, batch (what
is written in the graph), stored (the stored shapes) and ports (what the domain asks of the outside)."""

from .batch import GraphBatch, GraphLabel, GraphLink, GraphNode, GraphRelation, NodeKey, NodeWrite, Properties
from .concepts import (
    PageCoverage,
    ParsedOutput,
    ParseStatus,
    PreviewDocument,
    PreviewSection,
    RawFile,
    RawState,
    StoredParse,
)
from .ports import DocumentError, ParsedSink, ParseError, Parser, ParserUnavailable, RawSource, RunStore, SinkError
from .requests import ParsingRequest
from .results import (
    DocumentResult,
    DocumentState,
    ParsingRun,
    RunOutcome,
    RunProgress,
    RunStatus,
)
from .stored import ParsedJsonProperties, RawParseProperties, RawProperties, RunProperties

__all__ = [
    "DocumentError",
    "DocumentResult",
    "DocumentState",
    "GraphBatch",
    "GraphLabel",
    "GraphLink",
    "GraphNode",
    "GraphRelation",
    "NodeKey",
    "NodeWrite",
    "PageCoverage",
    "ParseError",
    "ParseStatus",
    "ParsedJsonProperties",
    "ParsedOutput",
    "ParsedSink",
    "Parser",
    "ParserUnavailable",
    "ParsingRequest",
    "ParsingRun",
    "PreviewDocument",
    "PreviewSection",
    "Properties",
    "RawFile",
    "RawParseProperties",
    "RawProperties",
    "RawSource",
    "RawState",
    "RunOutcome",
    "RunProgress",
    "RunProperties",
    "RunStatus",
    "RunStore",
    "SinkError",
    "StoredParse",
]
