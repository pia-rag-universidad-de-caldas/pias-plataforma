"""A question as a batch of data: its CONSULTA, the CHAT it belongs to and the chunks it cites, all in one batch so
that an answer is kept whole or not at all."""

from collections.abc import Sequence

from consultas.config import TITLE_LENGTH
from consultas.models import (
    ChatProperties,
    CitationProperties,
    GraphBatch,
    GraphLabel,
    GraphLink,
    GraphNode,
    GraphRelation,
    NodeKey,
    NodeWrite,
    QuestionProperties,
    Source,
)


def title(question: str) -> str:
    """The beginning of the first question, in one line."""
    line = " ".join(question.split())
    return line if len(line) <= TITLE_LENGTH else line[: TITLE_LENGTH - 1].rstrip() + "…"


def question_batch(
    chat: str,
    new_chat: bool,
    consulta: str,
    question: QuestionProperties,
    sources: Sequence[Source],
) -> GraphBatch:
    """The CONSULTA (new), its CHAT (created whole, or only its modificado_en) and a RESPONDIDA_CON to each cited
    chunk: a FRAGMENTOS, or an EXP_CHUNK if it was asked to an embeddings experiment."""
    when = question["creado_en"]
    chat_properties: ChatProperties = {"modificado_en": when}
    if new_chat:
        chat_properties = {
            "titulo": title(question["pregunta"]),
            "creado_en": when,
            "modificado_en": when,
            "laboratorio": question["laboratorio"],
        }
    chat_key, consulta_key = NodeKey(GraphLabel.CHAT, chat), NodeKey(GraphLabel.CONSULTA, consulta)
    chunk = GraphLabel.EXP_CHUNK if question["laboratorio"] else GraphLabel.FRAGMENTOS
    links = [GraphLink(GraphRelation.GENERA, chat_key, consulta_key)]
    for order, source in enumerate(sources, 1):
        citation: CitationProperties = {"puntaje": source.score, "orden": order}
        links.append(GraphLink(GraphRelation.RESPONDIDA_CON, consulta_key, NodeKey(chunk, source.id), citation))
    nodes = [GraphNode(chat_key, chat_properties), GraphNode(consulta_key, question, NodeWrite.REPLACE)]
    return GraphBatch(nodes, links)
