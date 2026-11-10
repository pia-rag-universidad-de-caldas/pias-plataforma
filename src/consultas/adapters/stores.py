"""The ports of consultas over data: the chats with their questions, and its active configuration.

Reading a chat walks data's relationships (data has no deep read): CHAT → CONSULTA → the chunks it cites, one request
per node. A chat is a handful of questions; if it weighs, the improvement goes in data, not here.
"""

from consultas.config import CONFIG_ID
from consultas.models import (
    ChatDetail,
    ChatSummary,
    ConfigProperties,
    ConsultasConfig,
    GraphBatch,
    GraphLabel,
    GraphNode,
    GraphRelation,
    NodeKey,
    StoredQuestion,
    Turn,
)

from . import mappers as to
from .data_client import DataClient

L, R = GraphLabel, GraphRelation
VECTOR = ("embedding",)  # left out of every read of a chunk: nothing here reads it back
_CHUNKS = {L.FRAGMENTOS.value: L.FRAGMENTOS, L.EXP_CHUNK.value: L.EXP_CHUNK}


class GraphChatStore:
    def __init__(self, data: DataClient) -> None:
        self._data = data

    def chat(self, id: str) -> ChatSummary | None:
        raw = self._data.node(L.CHAT, id)
        return None if raw is None else to.chat(id, raw)

    def _questions(self, chat: str, sources: bool) -> list[StoredQuestion]:
        found: list[StoredQuestion] = []
        for _, id, _ in self._data.outgoing(L.CHAT, chat, R.GENERA.value):
            raw = self._data.node(L.CONSULTA, id)
            if raw is None:
                continue
            cited = []
            for label, chunk, link in self._data.outgoing(L.CONSULTA, id, R.RESPONDIDA_CON.value) if sources else []:
                kind = _CHUNKS.get(label)
                cited.append(to.cited(chunk, label, link, self._data.node(kind, chunk, VECTOR) if kind else None))
            found.append(to.stored_question(id, raw, sorted(cited, key=lambda c: c.order)))
        return sorted(found, key=lambda q: (q.created, q.id))

    def history(self, id: str, turns: int) -> list[Turn]:
        questions = self._questions(id, sources=False)
        return [Turn(q.question, q.answer) for q in questions[-turns:]] if turns > 0 else []

    def save(self, batch: GraphBatch) -> None:
        self._data.save(batch)

    def chats(self) -> list[ChatSummary]:
        found = [to.chat(id, raw) for id, raw in self._data.nodes(L.CHAT)]
        return sorted(found, key=lambda c: (c.modified, c.id), reverse=True)

    def detail(self, id: str) -> ChatDetail | None:
        chat = self.chat(id)
        return None if chat is None else ChatDetail(chat, self._questions(id, sources=True))

    def delete(self, id: str) -> bool:
        """First its questions, in one transaction (they hang from the chat through GENERA, composition: data deletes
        them with replace_from; the chunks they cite stay), then the chat."""
        key = NodeKey(L.CHAT, id)
        if self.chat(id) is None:
            return False
        self._data.save(GraphBatch([GraphNode(key)], replace_from=key))
        return self._data.delete(L.CHAT, id)


class GraphConfigStore:
    """ConfigStore: the active configuration, this module's CONFIG_OFICIAL node."""

    def __init__(self, data: DataClient) -> None:
        self._data = data

    def active(self) -> ConsultasConfig | None:
        raw = self._data.node(L.CONFIG_OFICIAL, CONFIG_ID)
        return None if raw is None else to.config(raw)

    def set(self, config: ConsultasConfig) -> None:
        properties: ConfigProperties = {
            "modulo": CONFIG_ID,
            "k": config.k,
            "min_score": config.min_score,
            "prompt": config.prompt,
            "historia": config.history,
            "origen": config.origin.value,
            "modificado_en": config.modified or "",
        }
        self._data.save(GraphBatch([GraphNode(NodeKey(L.CONFIG_OFICIAL, CONFIG_ID), properties)]))

    def clear(self) -> bool:
        return self._data.delete(L.CONFIG_OFICIAL, CONFIG_ID)
