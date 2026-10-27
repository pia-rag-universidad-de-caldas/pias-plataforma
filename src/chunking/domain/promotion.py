"""Promotion (feature 028): what an approved experiment copies to the official graph, document by document.

A conversion-only experiment promotes its conversions:

    (:PIAA {id: codigo})-[:ES]->(:JSON {id: sha256, contenido...})-[:VIENE_DE]->(:EXP_DOCUMENTO)

replacing the JSON (and what hung from it: its old sections and chunks are stale). An experiment with a plan promotes
its sections and chunks under the official JSON, which must exist:

    (:JSON)-[:TIENE_SECCION]->(:SECCION {id: <sha256>:s<n>})-[:TIENE_FRAGMENTO]->(:FRAGMENTOS {id: <sha256>:<k>})

with `replace_from` = the JSON and the JSON itself only merged (its content stays). Ids as Hierarchy's (feature 023).
Property names and values are stored data: Spanish.
"""

from chunking.models import (
    CONVERTED,
    ChunkPiece,
    ChunkProperties,
    ConversionProperties,
    DocumentError,
    DocumentFailure,
    DocumentStatus,
    ExperimentDocument,
    ExperimentRecord,
    ExperimentSection,
    GraphBatch,
    GraphLabel,
    GraphLink,
    GraphNode,
    GraphRelation,
    NodeKey,
    NodeWrite,
    OfficialChunksProperties,
    OfficialJsonProperties,
    OfficialSectionProperties,
    PromotionKind,
    PromotionOutcome,
    PromotionStore,
    SourceDocument,
    rule_name,
)

from .hierarchy import Hierarchy


class Promotion:
    @staticmethod
    def kind(record: ExperimentRecord) -> PromotionKind:
        """Without a plan (stored as null) the experiment only converted."""
        return PromotionKind.CONVERSION if record.plan_json == "null" else PromotionKind.CHUNKS

    @staticmethod
    def conversion(stored: ConversionProperties, conversion_id: str, experiment: str, at: str) -> GraphBatch:
        """The official JSON of an approved conversion, its PIAA (ensured, never 000000) and its VIENE_DE."""
        sha256 = stored["sha256"]
        content = stored["contenido"]
        if stored["estado"] != CONVERTED or not isinstance(content, str):
            raise DocumentError("its conversion failed or has no content")
        document = SourceDocument(
            stored["origen"],
            stored["destino"],
            stored["nombre"],
            sha256,
            stored["tipo"],
            stored["anio"],
            stored["codigo"],
        )
        root = NodeKey(GraphLabel.JSON, Hierarchy.document_id(sha256))
        properties: OfficialJsonProperties = {
            "sha256": sha256,
            "origen": document.origin,
            "destino": document.target,
            "nombre": document.name,
            "tipo": document.file_type,
            "anio": document.year,
            "codigo": document.code,
            "contenido": content,
            "conversion": stored["conversion"],
            "fingerprint_conversion": stored["fingerprint_conversion"],
            "docling": stored["docling"],
            "secciones": stored["secciones"],
            "estado": DocumentStatus.CONVERTED.value,
            "error": None,
            "convertido_en": stored["convertido_en"],
            "oficializado_en": at,
            "experimento_conversion": experiment,
        }
        nodes, links = Hierarchy.piaa(document, root)
        nodes.append(GraphNode(root, properties))
        links.append(GraphLink(GraphRelation.VIENE_DE, root, NodeKey(GraphLabel.EXP_DOCUMENTO, conversion_id)))
        return GraphBatch(nodes, links, replace_from=root)

    @staticmethod
    def chunks(
        sha256: str,
        sections: list[ExperimentSection],
        chunks: list[tuple[int, ChunkPiece]],
        experiment: str,
        at: str,
    ) -> GraphBatch:
        """The sections and chunks of a document in an approved experiment, under its official JSON."""
        root = NodeKey(GraphLabel.JSON, Hierarchy.document_id(sha256))
        summary: OfficialChunksProperties = {
            "estado": DocumentStatus.CHUNKED.value,
            "fragmentos": len(chunks),
            "fragmentado_en": at,
            "experimento_chunks": experiment,
        }
        nodes = [GraphNode(root, summary, NodeWrite.MERGE)]
        links: list[GraphLink] = []
        keys: dict[int, NodeKey] = {}
        for section in sections:
            key = NodeKey(GraphLabel.SECCION, Hierarchy.section_id(sha256, section.index))
            keys[section.index] = key
            properties: OfficialSectionProperties = {
                "orden": section.index,
                "encabezados": [section.title] if section.title else [],
                "titulo": section.title,
                "paginas": section.pages,
                "regla": rule_name(section.rule),
                "estrategia": section.strategy,
                "parametros": section.parameters_json,
            }
            nodes.append(GraphNode(key, properties))
            links.append(GraphLink(GraphRelation.TIENE_SECCION, root, key))
        for index, (section_index, piece) in enumerate(chunks):
            parent = keys.get(section_index)
            if parent is None:
                raise DocumentError(f"chunk {index} belongs to section {section_index}, which isn't in the graph")
            key = NodeKey(GraphLabel.FRAGMENTOS, Hierarchy.chunk_id(sha256, index))
            chunk: ChunkProperties = {
                "indice": index,
                "texto": piece.text,
                "texto_contextualizado": "\n".join([*piece.headings, piece.text]),
                "encabezados": piece.headings,
                "paginas": piece.pages,
                "tokens": piece.tokens,
            }
            nodes.append(GraphNode(key, chunk))
            links.append(GraphLink(GraphRelation.TIENE_FRAGMENTO, parent, key))
        return GraphBatch(nodes, links, replace_from=root)

    @staticmethod
    def run(store: PromotionStore, record: ExperimentRecord, at: str) -> PromotionOutcome:
        """Promotes every document of the experiment that went well; the others (and the ones data rejects) are
        listed as failed. SinkError (data down) stops it: what was promoted stays (each document is atomic)."""
        kind = Promotion.kind(record)
        expected = DocumentStatus.CONVERTED if kind == PromotionKind.CONVERSION else DocumentStatus.CHUNKED
        promoted = 0
        failed: list[DocumentFailure] = []
        for document in store.documents(record.id):
            if document.status != expected:
                failed.append(
                    DocumentFailure(
                        document.error or f"it is {document.status.value}", document.origin, document.sha256
                    )
                )
                continue
            try:
                store.save(Promotion._batch(store, record.id, kind, document, at))
            except DocumentError as error:
                failed.append(DocumentFailure(str(error), document.origin, document.sha256))
                continue
            promoted += 1
        return PromotionOutcome(record.id, kind, promoted, failed)

    @staticmethod
    def _batch(
        store: PromotionStore, experiment: str, kind: PromotionKind, document: ExperimentDocument, at: str
    ) -> GraphBatch:
        if kind == PromotionKind.CONVERSION:
            stored = store.stored_conversion(document.conversion_id)
            if stored is None:
                raise DocumentError("its conversion is no longer in the graph")
            return Promotion.conversion(stored, document.conversion_id, experiment, at)
        if store.official(document.sha256) is None:
            raise DocumentError("it has no official JSON: promote its conversion first")
        sections = store.sections(experiment, document)
        return Promotion.chunks(document.sha256, sections, store.chunks(experiment, document), experiment, at)
