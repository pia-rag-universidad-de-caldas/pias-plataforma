"""ExperimentGraph: the batches that record an experiment in the graph (feature 043), with deterministic ids:

    (:EXPERIMENTO {id})-[:EXP_USA {chunks, tokens, estado, error, duracion}]->(:JSON {id: sha256})
    (:EXPERIMENTO)-[:EXP_GENERA]->(:EXP_SECCION {id: <experiment>:<sha256>:s<n>})
        -[:EXP_TIENE_CHUNK]->(:EXP_CHUNK {id: <experiment>:<sha256>:<k>})

EXP_USA is not composition: deleting an experiment never deletes the JSON. Property names and status values are stored
data: Spanish. The request and the results go as JSON text.
"""

import json
from dataclasses import asdict

from chunking.domain.production.graph import CHUNKED, FAILED, parameters_json
from chunking.domain.sections import chunk_properties, sections
from chunking.models import (
    Chunk,
    ExperimentProgress,
    ExperimentProperties,
    ExperimentRequest,
    ExperimentResults,
    ExperimentSectionProperties,
    ExperimentStatus,
    ExperimentUseProperties,
    GraphBatch,
    GraphLabel,
    GraphLink,
    GraphNode,
    GraphRelation,
    NodeKey,
    NodeWrite,
    RunStatus,
)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class ExperimentGraph:
    @staticmethod
    def experiment_key(id: str) -> NodeKey:
        return NodeKey(GraphLabel.EXPERIMENTO, id)

    @staticmethod
    def section_id(experiment: str, sha256: str, order: int) -> str:
        return f"{experiment}:{sha256}:s{order}"

    @staticmethod
    def chunk_id(experiment: str, sha256: str, index: int) -> str:
        return f"{experiment}:{sha256}:{index}"

    @staticmethod
    def documents_json(request: ExperimentRequest) -> str:
        return _json({"sha256s": list(dict.fromkeys(request.sha256s)), "from_experiment": request.from_experiment})

    @staticmethod
    def experiment(id: str, request: ExperimentRequest, files: int, at: str) -> GraphBatch:
        properties: ExperimentProperties = {
            "nombre": request.name,
            "descripcion": request.description,
            "creado_en": at,
            "estado": ExperimentStatus.QUEUED.value,
            "progreso": _json(asdict(ExperimentProgress(files=files))),
            "documentos": ExperimentGraph.documents_json(request),
            "chunking": parameters_json(request.parameters),
        }
        return GraphBatch([GraphNode(ExperimentGraph.experiment_key(id), properties)], [])

    @staticmethod
    def started(id: str, at: str) -> GraphBatch:
        """Its turn came."""
        properties = ExperimentProperties(estado=ExperimentStatus.RUNNING.value, iniciado_en=at)
        return GraphBatch([GraphNode(ExperimentGraph.experiment_key(id), properties, NodeWrite.MERGE)], [])

    @staticmethod
    def resumed(id: str, files: int) -> GraphBatch:
        """Back in line (feature 045): it ends again, over every document."""
        properties: ExperimentProperties = {
            "estado": ExperimentStatus.QUEUED.value,
            "progreso": _json(asdict(ExperimentProgress(files=files))),
            "terminado_en": None,
            "error": None,
        }
        return GraphBatch([GraphNode(ExperimentGraph.experiment_key(id), properties, NodeWrite.MERGE)], [])

    @staticmethod
    def status(error: str | None, failed: int) -> ExperimentStatus:
        return ExperimentStatus(RunStatus.ended(error, failed).value)

    @staticmethod
    def finish(
        id: str, results: ExperimentResults, progress: ExperimentProgress, error: str | None, at: str
    ) -> GraphBatch:
        properties: ExperimentProperties = {
            "estado": ExperimentGraph.status(error, results.errors).value,
            "terminado_en": at,
            "resultados": _json(asdict(results)),
            "progreso": _json(asdict(progress)),
            "error": error,
        }
        return GraphBatch([GraphNode(ExperimentGraph.experiment_key(id), properties, NodeWrite.MERGE)], [])

    @staticmethod
    def document(experiment: str, sha256: str, chunks: list[Chunk], error: str | None, seconds: float) -> GraphBatch:
        """What an experiment did with one document: its EXP_USA (with the summary) and, if it went well, an
        EXP_SECCION per heading path with its EXP_CHUNK."""
        root = ExperimentGraph.experiment_key(experiment)
        summary: ExperimentUseProperties = {
            "sha256": sha256,
            "estado": FAILED if error else CHUNKED,
            "error": error,
            "chunks": len(chunks),
            "tokens": sum(c.tokens for c in chunks),
            "duracion": round(seconds, 3),
            "tokens_por_chunk": [c.tokens for c in chunks],
        }
        nodes: list[GraphNode] = []
        links = [GraphLink(GraphRelation.EXP_USA, root, NodeKey(GraphLabel.JSON, sha256), summary)]
        keys: dict[tuple[str, ...], NodeKey] = {}
        for section in sections(chunks):
            key = NodeKey(GraphLabel.EXP_SECCION, ExperimentGraph.section_id(experiment, sha256, section.order))
            keys[tuple(section.headings)] = key
            properties = ExperimentSectionProperties(orden=section.order, encabezados=section.headings, sha256=sha256)
            nodes.append(GraphNode(key, properties))
            links.append(GraphLink(GraphRelation.EXP_GENERA, root, key))
        for chunk in chunks:
            key = NodeKey(GraphLabel.EXP_CHUNK, ExperimentGraph.chunk_id(experiment, sha256, chunk.index))
            nodes.append(GraphNode(key, chunk_properties(chunk)))
            links.append(GraphLink(GraphRelation.EXP_TIENE_CHUNK, keys[tuple(chunk.headings)], key))
        return GraphBatch(nodes, links)
