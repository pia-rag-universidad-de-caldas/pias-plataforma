"""GraphHttpSink (ChunkSink and ChunkCatalog, features 022 and 026): the production graph, written and read through
data over HTTP with GraphBatchClient and one GraphNodesClient per label; data's JSON becomes chunking models in
data/mappers.py.

    POST   {data}/batch                        a document with everything under it, all or nothing
    GET    {data}/nodes/JSON?page&per_page     what is already processed (paginated)
    GET    {data}/nodes/{label}/{id}[/relationships]
    DELETE {data}/nodes/JSON/{id}              a document replaced by another content of the same origin
"""

from collections.abc import Mapping

import httpx

from chunking.models import (
    Chunk,
    DocumentPage,
    GraphBatch,
    GraphLabel,
    GraphRelation,
    NodeKey,
    ProcessedDocument,
    Section,
)

from .data import GraphBatchClient, GraphNodesClient
from .data.mappers import chunk, integer, processed, properties, section


class GraphHttpSink:
    def __init__(self, client: httpx.Client, path: str) -> None:
        self._batch = GraphBatchClient(client, path)
        self._documents = GraphNodesClient(client, path, GraphLabel.JSON)
        self._sections = GraphNodesClient(client, path, GraphLabel.SECCION)
        self._chunks = GraphNodesClient(client, path, GraphLabel.FRAGMENTOS)

    # ChunkSink

    def save(self, batch: GraphBatch) -> int:
        self._batch.save(batch)
        return len(batch.nodes)

    def processed(self) -> dict[str, ProcessedDocument]:
        found: dict[str, ProcessedDocument] = {}
        for node in self._documents.all():
            document = processed(node)
            if document is not None:
                found[document.origin] = document
        return found

    def discard(self, sha256: str) -> None:
        self.save(GraphBatch([], [], replace_from=NodeKey(GraphLabel.JSON, sha256)))  # what hangs from it
        self._documents.delete(sha256)  # and the node (already gone: 404, fine)

    # ChunkCatalog

    def documents(self, page: int, per_page: int) -> DocumentPage:
        body = self._documents.page(page, per_page)
        documents = [d for d in map(processed, body.get("nodes") or []) if d is not None]
        return DocumentPage(page, per_page, integer(body.get("total")) or 0, integer(body.get("pages")) or 0, documents)

    def document(self, sha256: str) -> ProcessedDocument | None:
        return processed(self._documents.get(sha256))

    def chunks(self, sha256: str) -> tuple[list[Section], list[Chunk]]:
        sections: list[Section] = []
        chunks: list[Chunk] = []
        for section_id, _ in self._documents.outgoing(sha256, GraphRelation.TIENE_SECCION):
            node = self._sections.get(section_id)
            if not isinstance(node, Mapping):
                continue
            sections.append(section(properties(node) or {}))
            for chunk_id, _ in self._sections.outgoing(section_id, GraphRelation.TIENE_FRAGMENTO):
                node = self._chunks.get(chunk_id)
                if node is not None:
                    chunks.append(chunk(node))
        return sorted(sections, key=lambda s: s.order), sorted(chunks, key=lambda c: c.index)
