"""ComparisonStore over data (feature 060): the comparisons with their panels' questions.

Reading one walks data's relationships, like a chat: COMPARACION → CONSULTA (COMPARA) → the chunks it cites
(RESPONDIDA_CON), one request per node. A comparison has at most four panels.
"""

from consultas.models import (
    Comparison,
    ComparisonSummary,
    GraphBatch,
    GraphLabel,
    GraphNode,
    GraphRelation,
    NodeKey,
    PanelResult,
    PanelStatus,
    Source,
)

from . import mappers as to
from .data_client import DataClient

L, R = GraphLabel, GraphRelation
VECTOR = ("embedding",)  # left out of every read of a chunk: nothing here reads it back
_CHUNKS = {L.FRAGMENTOS.value: L.FRAGMENTOS, L.EXP_CHUNK.value: L.EXP_CHUNK}


class GraphComparisonStore:
    def __init__(self, data: DataClient) -> None:
        self._data = data

    def save(self, batch: GraphBatch) -> None:
        self._data.save(batch)

    def comparisons(self) -> list[ComparisonSummary]:
        found = [to.comparison_summary(id, raw) for id, raw in self._data.nodes(L.COMPARACION)]
        return sorted(found, key=lambda c: (c.created, c.id), reverse=True)

    def _sources(self, consulta: str) -> list[Source]:
        cited: list[tuple[int, Source]] = []
        for label, chunk, link in self._data.outgoing(L.CONSULTA, consulta, R.RESPONDIDA_CON.value):
            kind = _CHUNKS.get(label)
            cited.append(to.cited_source(chunk, link, self._data.node(kind, chunk, VECTOR) if kind else None))
        return [source for _, source in sorted(cited, key=lambda c: c[0])]

    def _panel(self, result: PanelResult, consulta: str | None) -> PanelResult:
        """With its answer, if it has its CONSULTA (a failed panel has none)."""
        raw = None if consulta is None else self._data.node(L.CONSULTA, consulta)
        if consulta is None or raw is None:
            if result.status is PanelStatus.OK:  # its question is no longer there
                return PanelResult(
                    result.index, result.label, result.against, result.llm, result.k, PanelStatus.ERROR,
                    f"its question {consulta!r} is no longer in data",
                )  # fmt: skip
            return result
        answer = to.panel_answer(consulta, raw, self._sources(consulta))
        return PanelResult(
            result.index, result.label, result.against, result.llm, result.k, result.status, result.error, answer
        )

    def detail(self, id: str) -> Comparison | None:
        raw = self._data.node(L.COMPARACION, id)
        if raw is None:
            return None
        summary = to.comparison_summary(id, raw)
        panels = [self._panel(result, consulta) for result, consulta, _ in to.stored_panels(raw)]
        return Comparison(id, summary.question, summary.created, panels)

    def delete(self, id: str) -> bool:
        """First its questions, in one transaction (they hang from the comparison through COMPARA, composition: data
        deletes them with replace_from; the chunks they cite stay), then the comparison."""
        key = NodeKey(L.COMPARACION, id)
        if self._data.node(L.COMPARACION, id) is None:
            return False
        self._data.save(GraphBatch([GraphNode(key)], replace_from=key))
        return self._data.delete(L.COMPARACION, id)
