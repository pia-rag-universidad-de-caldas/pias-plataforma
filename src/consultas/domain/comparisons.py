"""A comparison as a batch of data (feature 060): its COMPARACION, the CONSULTA of each panel that answered (without a
CHAT) and the chunks each one cites, in one batch, so that a comparison is kept whole or not at all.

A panel that failed stores no CONSULTA (it has no answer nor citations): its configuration, state and error stay in
the `paneles` JSON of the COMPARACION. A comparison's CONSULTA keeps what shows it again as it was answered: the
seconds of each step, what each attachment searched with, the courses it named and, in each citation, what the search
said of the chunk."""

import json
from collections.abc import Sequence
from dataclasses import dataclass

from consultas.models import (
    Against,
    AttachmentUse,
    CitationProperties,
    ComparedProperties,
    ComparisonProperties,
    CourseMatch,
    GraphBatch,
    GraphLabel,
    GraphLink,
    GraphNode,
    GraphRelation,
    LlmOptions,
    LlmProperties,
    NodeKey,
    NodeWrite,
    PanelProperties,
    PanelResult,
    QuestionProperties,
    Response,
    Source,
    TargetProperties,
)


@dataclass(frozen=True)
class Asked:
    """A panel as it went: its result and, if it answered, what to store of it."""

    result: PanelResult
    response: Response | None = None


def target_properties(against: Against | None) -> TargetProperties | None:
    if against is None:
        return None
    if against.embeddings_experiment is not None:
        return {"experimento_embedding": against.embeddings_experiment}
    return {"modelo_embedding": against.embeddings_model or ""}


def llm_properties(options: LlmOptions) -> LlmProperties:
    found: LlmProperties = {}
    if options.model is not None:
        found["modelo"] = options.model
    if options.temperature is not None:
        found["temperatura"] = options.temperature
    if options.num_ctx is not None:
        found["num_ctx"] = options.num_ctx
    if options.max_tokens is not None:
        found["max_tokens"] = options.max_tokens
    return found


def _use(use: AttachmentUse) -> dict[str, object]:
    return {
        "nombre": use.name,
        "mime": use.mime,
        "tipo": use.kind.value,
        "trozos": use.pieces,
        "caracteres": use.characters,
        "truncado": use.truncated,
        "descripcion": use.description,
    }


def _course(course: CourseMatch) -> dict[str, object]:
    return {
        "sha256": course.sha256,
        "nombre": course.name,
        "codigo_actividad": course.activity_code,
        "puntaje": course.score,
        "origen": course.origin,
    }


def compared_question(response: Response) -> QuestionProperties:
    """The CONSULTA of a panel: /ask's, plus what shows it again as it was answered."""
    stored: QuestionProperties = {**response.stored}
    stored["segundos_busqueda"] = response.seconds.search
    stored["segundos_respuesta"] = response.seconds.answer
    stored["uso_adjuntos"] = json.dumps([_use(u) for u in response.attachments], ensure_ascii=False)
    stored["cursos"] = json.dumps([_course(c) for c in response.courses], ensure_ascii=False)
    return stored


def citation(source: Source, order: int) -> CitationProperties:
    found: CitationProperties = {"puntaje": source.score, "orden": order, "sha256": source.sha256}
    if source.origin is not None:
        found["origen"] = source.origin
    if source.code is not None:
        found["codigo"] = source.code
    if source.activity is not None:
        found["actividad"] = source.activity
    return found


def panel_properties(result: PanelResult) -> PanelProperties:
    answer = result.answer
    return {
        "indice": result.index,
        "etiqueta": result.label,
        "destino": target_properties(result.against),
        "llm": llm_properties(result.llm),
        "k": result.k,
        "estado": result.status.value,
        "error": result.error,
        "consulta": None if answer is None else answer.consulta,
        "modelo_llm": None if answer is None else answer.model,
    }


def comparison_batch(id: str, question: str, created: str, panels: Sequence[Asked]) -> GraphBatch:
    """The COMPARACION (new), the CONSULTA of each panel that answered with its COMPARA, and a RESPONDIDA_CON to each
    chunk it cites: a FRAGMENTOS, or an EXP_CHUNK if the panel asked an embeddings experiment."""
    key = NodeKey(GraphLabel.COMPARACION, id)
    comparison: ComparisonProperties = {
        "pregunta": question,
        "creado_en": created,
        "paneles": json.dumps([panel_properties(p.result) for p in panels], ensure_ascii=False),
        "laboratorio": any(p.result.against is not None and p.result.against.laboratory for p in panels),
    }
    nodes = [GraphNode(key, comparison, NodeWrite.REPLACE)]
    links: list[GraphLink] = []
    for panel in panels:
        answer, response = panel.result.answer, panel.response
        if answer is None or response is None:
            continue
        consulta = NodeKey(GraphLabel.CONSULTA, answer.consulta)
        nodes.append(GraphNode(consulta, compared_question(response), NodeWrite.REPLACE))
        compared: ComparedProperties = {"panel": panel.result.index, "etiqueta": panel.result.label}
        links.append(GraphLink(GraphRelation.COMPARA, key, consulta, compared))
        chunk = GraphLabel.EXP_CHUNK if response.laboratory else GraphLabel.FRAGMENTOS
        for order, source in enumerate(response.sources, 1):
            links.append(
                GraphLink(GraphRelation.RESPONDIDA_CON, consulta, NodeKey(chunk, source.id), citation(source, order))
            )
    return GraphBatch(nodes, links)
