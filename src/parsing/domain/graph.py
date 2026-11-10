"""ParsedGraph: the batch of a parsed document, (:PIAA)-[:ES]->(:JSON)-[:VIENE_DE]->(:RAW), with deterministic ids:
the JSON and the RAW are the sha256, the PIAA its code (never 000000)."""

from parsing.config import UNASSIGNED_CODE
from parsing.models import (
    GraphBatch,
    GraphLabel,
    GraphLink,
    GraphNode,
    GraphRelation,
    NodeKey,
    NodeWrite,
    ParsedJsonProperties,
    ParsedOutput,
    ParseStatus,
    RawFile,
    RawParseProperties,
)

from .codec import encode


class ParsedGraph:
    @staticmethod
    def status(output: ParsedOutput) -> ParseStatus:
        return ParseStatus.PARSED if output.coverage.complete else ParseStatus.PARTIAL

    @staticmethod
    def parsed(
        raw: RawFile, output: ParsedOutput, fingerprint: str, docling: str, at: str, seconds: float
    ) -> GraphBatch:
        """The JSON is written whole (replace) and what hung from it (the chunks of an earlier parsing) is deleted:
        it no longer matches the document. The RAW keeps ingesta's properties (merge); the PIAA, if any, isn't
        touched (ensure)."""
        status, coverage = ParsedGraph.status(output), output.coverage
        document, size = encode(output.document)
        json_key = NodeKey(GraphLabel.JSON, raw.sha256)
        raw_key = NodeKey(GraphLabel.RAW, raw.sha256)
        properties: ParsedJsonProperties = {
            "sha256": raw.sha256,
            "estado": status.value,
            "error": coverage.reason,
            "fingerprint_parseo": fingerprint,
            "docling": docling,
            "parseado_en": at,
            "duracion_parseo": round(seconds, 1),
            "paginas_totales": coverage.total,
            "paginas_procesadas": coverage.processed,
            "paginas_pendientes": coverage.pending,
            "paginas_sin_texto": coverage.without_text,
            "paginas_ocr": output.ocr_pages,
            "documento": document,
            "documento_bytes": size,
        }
        state: RawParseProperties = {
            "parseado": True,
            "estado_parseo": status.value,
            "parseado_en": at,
            "fingerprint_parseo": fingerprint,
            "error_parseo": coverage.reason,
        }
        nodes = [
            GraphNode(json_key, properties, NodeWrite.REPLACE),
            GraphNode(raw_key, state, NodeWrite.MERGE),
        ]
        links = [GraphLink(GraphRelation.VIENE_DE, json_key, raw_key)]
        if raw.code and raw.code != UNASSIGNED_CODE:
            piaa = NodeKey(GraphLabel.PIAA, raw.code)
            nodes.append(GraphNode(piaa, {}, NodeWrite.ENSURE))
            links.append(GraphLink(GraphRelation.ES, piaa, json_key))
        return GraphBatch(nodes, links, replace_from=json_key)

    @staticmethod
    def failed(sha256: str, error: str) -> GraphBatch:
        """Only the RAW says it failed: an earlier good JSON stays as it was."""
        state: RawParseProperties = {"estado_parseo": ParseStatus.ERROR.value, "error_parseo": error}
        return GraphBatch([GraphNode(NodeKey(GraphLabel.RAW, sha256), state, NodeWrite.MERGE)])
