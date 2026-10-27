"""Hierarchy: the graph batch of a document, (:PIAA)-[:ES]->(:JSON)-[:TIENE_SECCION]->(:SECCION)-[:TIENE_FRAGMENTO]->
(:FRAGMENTOS), with deterministic ids so that chunking a document again replaces it instead of duplicating it.

Property names (and the status values) are stored in Neo4j: they stay in Spanish. The PIAA only gets its id (the code)
and is only ensured: what another load puts on it (its ASIGNATURA, ...) is never touched.
"""

from chunking.config import UNASSIGNED_CODE
from chunking.models import (
    Chunk,
    ChunkedDocument,
    ChunkingParameters,
    ChunkProperties,
    DocumentStatus,
    GraphBatch,
    GraphLabel,
    GraphLink,
    GraphNode,
    GraphRelation,
    JsonProperties,
    NodeKey,
    NodeWrite,
    ParametersProperties,
    Section,
    SectionProperties,
    SourceDocument,
)

type HeadingPath = tuple[str, ...]


class Hierarchy:
    @staticmethod
    def document_id(sha256: str) -> str:
        return sha256

    @staticmethod
    def section_id(sha256: str, order: int) -> str:
        return f"{sha256}:s{order}"

    @staticmethod
    def chunk_id(sha256: str, index: int) -> str:
        return f"{sha256}:{index}"

    @staticmethod
    def parameters(parameters: ChunkingParameters) -> ParametersProperties:
        """The chunking parameters as JSON node properties (stored data: Spanish names, as GraphHttpSink reads them)."""
        return {
            "tokenizador": parameters.tokenizer,
            "max_tokens": parameters.max_tokens,
            "fusionar_vecinos": parameters.merge_peers,
            "repetir_encabezado_tabla": parameters.repeat_table_header,
            "estructura_tablas": parameters.table_structure,
            "modo_tablas": parameters.table_mode.value,
            "docling": parameters.docling_version,
        }

    @staticmethod
    def sections(chunks: list[Chunk]) -> list[Section]:
        """One section per distinct heading path, by first appearance (the chunks without headings share one)."""
        paths: dict[HeadingPath, int] = {}
        for chunk in chunks:
            paths.setdefault(tuple(chunk.headings), len(paths))
        return [Section(order, list(path)) for path, order in paths.items()]

    @staticmethod
    def build(
        document: SourceDocument, chunked: ChunkedDocument, parameters: ChunkingParameters, at: str
    ) -> GraphBatch:
        """The document as chunked: its JSON node, sections and chunks, replacing what it had."""
        sha256 = Hierarchy._sha256(document)
        root = NodeKey(GraphLabel.JSON, Hierarchy.document_id(sha256))
        properties = Hierarchy._document(
            document, sha256, parameters, at, DocumentStatus.CHUNKED, None, len(chunked.chunks)
        )
        nodes, links = Hierarchy.piaa(document, root)
        nodes.append(GraphNode(root, properties))
        sections = Hierarchy.sections(chunked.chunks)
        keys = {tuple(s.headings): NodeKey(GraphLabel.SECCION, Hierarchy.section_id(sha256, s.order)) for s in sections}
        for section in sections:
            key = keys[tuple(section.headings)]
            nodes.append(GraphNode(key, SectionProperties(orden=section.order, encabezados=section.headings)))
            links.append(GraphLink(GraphRelation.TIENE_SECCION, root, key))
        for chunk in chunked.chunks:
            key = NodeKey(GraphLabel.FRAGMENTOS, Hierarchy.chunk_id(sha256, chunk.index))
            nodes.append(GraphNode(key, Hierarchy._chunk(chunk)))
            links.append(GraphLink(GraphRelation.TIENE_FRAGMENTO, keys[tuple(chunk.headings)], key))
        return GraphBatch(nodes, links, replace_from=root)

    @staticmethod
    def failed(document: SourceDocument, error: str, parameters: ChunkingParameters, at: str) -> GraphBatch:
        """The document as failed, with its reason and without chunks (what it had is removed: it is stale)."""
        sha256 = Hierarchy._sha256(document)
        root = NodeKey(GraphLabel.JSON, Hierarchy.document_id(sha256))
        properties = Hierarchy._document(document, sha256, parameters, at, DocumentStatus.ERROR, error, 0)
        nodes, links = Hierarchy.piaa(document, root)
        nodes.append(GraphNode(root, properties))
        return GraphBatch(nodes, links, replace_from=root)

    @staticmethod
    def _sha256(document: SourceDocument) -> str:
        if not document.sha256:
            raise ValueError(f"{document.origin} has no sha256: it can't be stored in the graph")
        return document.sha256

    @staticmethod
    def _document(
        document: SourceDocument,
        sha256: str,
        parameters: ChunkingParameters,
        at: str,
        status: DocumentStatus,
        error: str | None,
        chunks: int,
    ) -> JsonProperties:
        return {
            "origen": document.origin,
            "destino": document.target,
            "nombre": document.name,
            "tipo": document.file_type,
            "anio": document.year,
            "codigo": document.code,
            "sha256": sha256,
            "fingerprint": parameters.fingerprint,
            **Hierarchy.parameters(parameters),
            "estado": status.value,
            "error": error,
            "fragmentado_en": at,
            "fragmentos": chunks,
        }

    @staticmethod
    def piaa(document: SourceDocument, root: NodeKey) -> tuple[list[GraphNode], list[GraphLink]]:
        """The PIAA of the document (only ensured, with just its id) and its ES; nothing for 000000 or no code."""
        if not document.code or document.code == UNASSIGNED_CODE:
            return [], []
        piaa = NodeKey(GraphLabel.PIAA, document.code)
        return [GraphNode(piaa, mode=NodeWrite.ENSURE)], [GraphLink(GraphRelation.ES, piaa, root)]

    @staticmethod
    def _chunk(chunk: Chunk) -> ChunkProperties:
        return {
            "indice": chunk.index,
            "texto": chunk.text,
            "texto_contextualizado": chunk.contextualized_text,
            "encabezados": chunk.headings,
            "paginas": chunk.pages,
            "tokens": chunk.tokens,
        }
