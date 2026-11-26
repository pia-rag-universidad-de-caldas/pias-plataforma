"""OfficialGraph: what a run writes under a JSON (features 043 and 045), with deterministic ids so that chunking a
document again replaces it instead of duplicating it:

    (:JSON {id: sha256})-[:TIENE_SECCION]->(:SECCION {id: <sha256>:s<n>})
        -[:TIENE_FRAGMENTO]->(:FRAGMENTOS {id: <sha256>:<k>})

The JSON is parsing's (feature 042): chunking only merges its own properties on it, never the parse's. RunGraph: a run
as a node (CORRIDA_CHUNKING), so that it outlives the server and can be resumed.
"""

import json
from dataclasses import asdict

from chunking.domain.sections import chunk_properties, parameters_properties, sections
from chunking.models import (
    Chunk,
    ChunkingParameters,
    ChunkingRun,
    GraphBatch,
    GraphLabel,
    GraphLink,
    GraphNode,
    GraphRelation,
    JsonChunkingFailure,
    JsonChunkingMark,
    JsonChunkingProperties,
    NodeKey,
    NodeWrite,
    RunProperties,
    SectionProperties,
    chunked_fingerprint,
)

CHUNKED = "fragmentado"  # JSON.estado_chunking
FAILED = "error"


class OfficialGraph:
    @staticmethod
    def document_key(sha256: str) -> NodeKey:
        return NodeKey(GraphLabel.JSON, sha256)

    @staticmethod
    def section_id(sha256: str, order: int) -> str:
        return f"{sha256}:s{order}"

    @staticmethod
    def chunk_id(sha256: str, index: int) -> str:
        return f"{sha256}:{index}"

    @staticmethod
    def chunked(
        sha256: str,
        chunks: list[Chunk],
        parameters: ChunkingParameters,
        parse_fingerprint: str,
        at: str,
        experiment: str | None,
    ) -> GraphBatch:
        """Its sections and chunks, replacing what hung from the JSON, and the chunking's properties on it."""
        root = OfficialGraph.document_key(sha256)
        properties: JsonChunkingProperties = {
            **parameters_properties(parameters),
            "estado_chunking": CHUNKED,
            "error_chunking": None,
            "huella_chunking": chunked_fingerprint(parameters, parse_fingerprint),
            "config_chunking": parameters.fingerprint,
            "parseo_chunkeado": parse_fingerprint,
            "fragmentado_en": at,
            "fragmentos": len(chunks),
            "experimento_config": experiment,
        }
        nodes = [GraphNode(root, properties, NodeWrite.MERGE)]
        links: list[GraphLink] = []
        keys: dict[tuple[str, ...], NodeKey] = {}
        for section in sections(chunks):
            key = NodeKey(GraphLabel.SECCION, OfficialGraph.section_id(sha256, section.order))
            keys[tuple(section.headings)] = key
            nodes.append(GraphNode(key, SectionProperties(orden=section.order, encabezados=section.headings)))
            links.append(GraphLink(GraphRelation.TIENE_SECCION, root, key))
        for chunk in chunks:
            key = NodeKey(GraphLabel.FRAGMENTOS, OfficialGraph.chunk_id(sha256, chunk.index))
            nodes.append(GraphNode(key, chunk_properties(chunk)))
            links.append(GraphLink(GraphRelation.TIENE_FRAGMENTO, keys[tuple(chunk.headings)], key))
        return GraphBatch(nodes, links, replace_from=root)

    @staticmethod
    def marked(sha256: str, parameters: ChunkingParameters, parse_fingerprint: str) -> GraphBatch:
        """One already chunked with these parameters before feature 045: only what data counts with is added."""
        properties: JsonChunkingMark = {
            "config_chunking": parameters.fingerprint,
            "parseo_chunkeado": parse_fingerprint,
        }
        return GraphBatch([GraphNode(OfficialGraph.document_key(sha256), properties, NodeWrite.MERGE)], [])

    @staticmethod
    def failed(sha256: str, error: str, had_chunks: bool) -> GraphBatch:
        """A failure: only its error (and the state, if it had no chunks); the chunks it had stay, and nothing marks it
        as done, so the next run tries it again."""
        properties: JsonChunkingFailure = {"error_chunking": error}
        if not had_chunks:
            properties["estado_chunking"] = FAILED
        return GraphBatch([GraphNode(OfficialGraph.document_key(sha256), properties, NodeWrite.MERGE)], [])


def parameters_json(parameters: ChunkingParameters) -> str:
    return json.dumps(asdict(parameters), ensure_ascii=False, sort_keys=True)


class RunGraph:
    @staticmethod
    def record(run: ChunkingRun) -> GraphBatch:
        """Everything it has now: it is written again each time it changes."""
        properties: RunProperties = {
            "estado": run.status.value,
            "pedido_en": run.requested,
            "inicio": run.started,
            "fin": run.finished,
            "simulacion": run.simulate,
            "parametros": parameters_json(run.parameters),
            "experimento_config": run.experiment,
            "documentos": json.dumps(run.sha256s),
            "congelada": run.frozen,
            "pagina": run.page,
            "por_pagina": run.per_page,
            "progreso": json.dumps(asdict(run.progress)),
            "fallos": json.dumps([asdict(f) for f in run.failures], ensure_ascii=False),
            "fragmentados": json.dumps(run.chunked),
            "error": run.error,
            "retomada": run.resumed,
        }
        key = NodeKey(GraphLabel.CORRIDA_CHUNKING, run.id)
        return GraphBatch([GraphNode(key, properties, NodeWrite.MERGE)], [])
