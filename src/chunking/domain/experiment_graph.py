"""ExperimentGraph: the batches that record an experiment in the graph (feature 025), with deterministic ids:

    (:EXPERIMENTO {id})-[:EXP_USA]->(:EXP_DOCUMENTO {id: <sha256>:<conversion fingerprint>})
        -[:EXP_TIENE_SECCION]->(:EXP_SECCION {id: <experiment>:<sha256>:<n>})
        -[:EXP_TIENE_CHUNK]->(:EXP_CHUNK {id: <experiment>:<sha256>:<n>:<k>})
    (:EXPERIMENTO)-[:EXP_GENERA]->(:EXP_SECCION)

Property names and status values are stored data: Spanish. The request and the results go as JSON text.
"""

import json
from dataclasses import asdict

from chunking.models import (
    CONVERSION_FAILED,
    CONVERTED,
    ChunkPiece,
    ConversionParameters,
    ConversionProperties,
    ConvertedDocument,
    DocumentStatus,
    ExperimentChunkProperties,
    ExperimentProgress,
    ExperimentProperties,
    ExperimentRequest,
    ExperimentResults,
    ExperimentSectionProperties,
    ExperimentStatus,
    ExperimentUseProperties,
    FileSelection,
    GraphBatch,
    GraphLabel,
    GraphLink,
    GraphNode,
    GraphRelation,
    NodeKey,
    NodeWrite,
    OfficialDocument,
    PageRange,
    Plan,
    SectionAssignment,
    SourceDocument,
    StrategyParameters,
    rule_name,
)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _pages(pages: PageRange | None) -> dict[str, int] | None:
    return {"from": pages.first, "to": pages.last} if pages else None


def strategy_json(parameters: StrategyParameters) -> dict[str, object]:
    """The resolved parameters of a strategy, without the ones it doesn't use."""
    return {k: v for k, v in asdict(parameters).items() if v is not None}


class ExperimentGraph:
    @staticmethod
    def experiment_key(id: str) -> NodeKey:
        return NodeKey(GraphLabel.EXPERIMENTO, id)

    @staticmethod
    def conversion_id(sha256: str, conversion: ConversionParameters) -> str:
        return f"{sha256}:{conversion.fingerprint}"

    @staticmethod
    def section_id(experiment: str, sha256: str, index: int) -> str:
        return f"{experiment}:{sha256}:{index}"

    @staticmethod
    def chunk_id(experiment: str, sha256: str, section: int, index: int) -> str:
        return f"{experiment}:{sha256}:{section}:{index}"

    @staticmethod
    def files_json(files: FileSelection) -> dict[str, object]:
        """The files asked for, as stored (the forms not used are null or empty)."""
        official = files.from_json
        return {
            "sha256s": files.sha256s,
            "filter": asdict(files.filter) if files.filter else None,
            "limit": files.limit,
            "all": files.all,
            "pages": _pages(files.pages),
            "per_page": files.per_page,
            "from_experiment": files.from_experiment,
            "from_json": {
                "all": official.all,
                "pages": _pages(official.pages),
                "per_page": official.per_page,
                "sha256s": official.sha256s,
            }
            if official
            else None,
        }

    @staticmethod
    def plan_json(plan: Plan | None) -> dict[str, object] | None:
        if plan is None:
            return None
        return {
            "rules": [
                {
                    "match": {
                        "titles": r.match.titles,
                        "position": {"from": r.match.position.start, "to": r.match.position.end}
                        if r.match.position
                        else None,
                    },
                    "chunking": strategy_json(r.chunking),
                }
                for r in plan.rules
            ],
            "default": strategy_json(plan.default),
        }

    @staticmethod
    def request_properties(request: ExperimentRequest) -> ExperimentProperties:
        """The request as stored: what was asked, with every default resolved (to repeat it exactly). Without a
        plan (conversion only) it is null; from official JSON the conversion is null (each JSON keeps its own)."""
        conversion = None if request.files.from_json else asdict(request.conversion)
        return {
            "archivos": _json(ExperimentGraph.files_json(request.files)),
            "conversion": _json(conversion),
            "plan": _json(ExperimentGraph.plan_json(request.plan)),
        }

    @staticmethod
    def experiment(id: str, request: ExperimentRequest, files: int, at: str) -> GraphBatch:
        properties: ExperimentProperties = {
            "nombre": request.name,
            "descripcion": request.description,
            "creado_en": at,
            "estado": ExperimentStatus.RUNNING.value,
            "progreso": _json(asdict(ExperimentProgress(files=files))),
            **ExperimentGraph.request_properties(request),
        }
        return GraphBatch([GraphNode(ExperimentGraph.experiment_key(id), properties)], [])

    @staticmethod
    def progress(id: str, progress: ExperimentProgress) -> GraphBatch:
        properties = ExperimentProperties(progreso=_json(asdict(progress)))
        node = GraphNode(ExperimentGraph.experiment_key(id), properties, NodeWrite.MERGE)
        return GraphBatch([node], [])

    @staticmethod
    def finish(
        id: str, results: ExperimentResults, progress: ExperimentProgress, error: str | None, at: str
    ) -> GraphBatch:
        properties: ExperimentProperties = {
            "estado": (ExperimentStatus.FAILED if error else ExperimentStatus.FINISHED).value,
            "terminado_en": at,
            "resultados": _json(asdict(results)),
            "progreso": _json(asdict(progress)),
            "error": error,
        }
        return GraphBatch([GraphNode(ExperimentGraph.experiment_key(id), properties, NodeWrite.MERGE)], [])

    @staticmethod
    def conversion(
        document: SourceDocument,
        sha256: str,
        conversion: ConversionParameters,
        converted: ConvertedDocument | None,
        error: str | None,
        seconds: float,
        at: str,
    ) -> GraphBatch:
        """The EXP_DOCUMENTO: the file (as ingesta describes it), its conversion and with what it was made."""
        properties: ConversionProperties = {
            "sha256": sha256,
            "origen": document.origin,
            "destino": document.target,
            "nombre": document.name,
            "tipo": document.file_type,
            "anio": document.year,
            "codigo": document.code,
            "conversion": _json(asdict(conversion)),
            "fingerprint_conversion": conversion.fingerprint,
            "docling": conversion.docling_version,
            "estado": CONVERTED if converted is not None else CONVERSION_FAILED,
            "error": error,
            "contenido": converted.to_json() if converted is not None else None,
            "secciones": len(converted.sections) if converted is not None else 0,
            "duracion_conversion": round(seconds, 3),
            "convertido_en": at,
        }
        key = NodeKey(GraphLabel.EXP_DOCUMENTO, ExperimentGraph.conversion_id(sha256, conversion))
        return GraphBatch([GraphNode(key, properties)], [])

    @staticmethod
    def restored_conversion(official: OfficialDocument, at: str) -> GraphBatch:
        """The EXP_DOCUMENTO an official JSON came from, rebuilt from it if it is no longer in the graph (`ensure`:
        an existing one is never touched), so that an experiment over official JSON can use it (feature 028)."""
        content = official.content
        document = official.document
        properties: ConversionProperties = {
            "sha256": document.sha256 or "",
            "origen": document.origin,
            "destino": document.target,
            "nombre": document.name,
            "tipo": document.file_type,
            "anio": document.year,
            "codigo": document.code,
            "conversion": official.conversion_json or "null",
            "fingerprint_conversion": official.conversion_id.split(":", 1)[-1],
            "docling": official.docling,
            "estado": CONVERTED,
            "error": None,
            "contenido": content.to_json() if content is not None else None,
            "secciones": len(content.sections) if content is not None else 0,
            "duracion_conversion": 0.0,
            "convertido_en": at,
        }
        key = NodeKey(GraphLabel.EXP_DOCUMENTO, official.conversion_id)
        return GraphBatch([GraphNode(key, properties, NodeWrite.ENSURE)], [])

    @staticmethod
    def document(
        experiment: str,
        document: SourceDocument,
        sha256: str,
        conversion_id: str,
        reused: bool,
        assignments: list[tuple[SectionAssignment, list[ChunkPiece]]],
        error: str | None,
        seconds: float,
        chunked: bool = True,
    ) -> GraphBatch:
        """What an experiment did with one document: its EXP_USA (with the summary) and, if it went well, an
        EXP_SECCION per section (rule, strategy, parameters) with its EXP_CHUNK. `chunked` False: a conversion-only
        experiment (feature 028), the document is only `convertido`."""
        root = ExperimentGraph.experiment_key(experiment)
        doc = NodeKey(GraphLabel.EXP_DOCUMENTO, conversion_id)
        nodes: list[GraphNode] = []
        links: list[GraphLink] = []
        chunks = 0
        for assignment, pieces in assignments:
            section = assignment.section
            key = NodeKey(GraphLabel.EXP_SECCION, ExperimentGraph.section_id(experiment, sha256, assignment.index))
            nodes.append(
                GraphNode(
                    key,
                    ExperimentSectionProperties(
                        indice=assignment.index,
                        titulo=section.title,
                        nivel=section.level,
                        paginas=section.pages,
                        regla=rule_name(assignment.rule),
                        estrategia=assignment.parameters.strategy.value,
                        parametros=_json(strategy_json(assignment.parameters)),
                        chunks=len(pieces),
                        tokens=sum(p.tokens for p in pieces),
                    ),
                )
            )
            links += [
                GraphLink(GraphRelation.EXP_GENERA, root, key),
                GraphLink(GraphRelation.EXP_TIENE_SECCION, doc, key),
            ]
            for k, piece in enumerate(pieces):
                chunk = NodeKey(GraphLabel.EXP_CHUNK, ExperimentGraph.chunk_id(experiment, sha256, assignment.index, k))
                nodes.append(
                    GraphNode(
                        chunk,
                        ExperimentChunkProperties(
                            indice=k,
                            texto=piece.text,
                            encabezados=piece.headings,
                            paginas=piece.pages,
                            tokens=piece.tokens,
                        ),
                    )
                )
                links.append(GraphLink(GraphRelation.EXP_TIENE_CHUNK, key, chunk))
            chunks += len(pieces)
        summary: ExperimentUseProperties = {
            "sha256": sha256,
            "origen": document.origin,
            "nombre": document.name,
            "codigo": document.code,
            "reutilizado": reused,
            "estado": (
                DocumentStatus.ERROR if error else DocumentStatus.CHUNKED if chunked else DocumentStatus.CONVERTED
            ).value,
            "error": error,
            "secciones": len(assignments),
            "chunks": chunks,
            "duracion_chunking": round(seconds, 3),
        }
        links.insert(0, GraphLink(GraphRelation.EXP_USA, root, doc, summary))
        return GraphBatch(nodes, links)
