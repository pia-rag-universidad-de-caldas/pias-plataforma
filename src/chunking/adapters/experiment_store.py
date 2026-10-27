"""GraphExperimentStore (ExperimentStore, features 025 and 026): the experiment record in the graph, through data over
HTTP with GraphBatchClient and one GraphNodesClient per label; data's JSON becomes chunking models in
data/experiment_mappers.py.

    POST   {data}/batch                                   EXPERIMENTO, EXP_DOCUMENTO, EXP_SECCION, EXP_CHUNK, scores,
                                                          official JSON, SECCION, FRAGMENTOS (promote, feature 028)
    GET    {data}/nodes/EXPERIMENTO[/{id}[/relationships]]
    GET    {data}/nodes/{EXP_DOCUMENTO|EXP_SECCION|EXP_CHUNK|EXP_PUNTUACION}/{id}
    GET    {data}/nodes/JSON[?page&per_page | /{sha256}]          official JSON (feature 028)
    DELETE {data}/nodes/{EXPERIMENTO|EXP_PUNTUACION}/{id}
"""

from collections.abc import Iterator

import httpx

from chunking.models import (
    CONVERTED,
    ChunkPiece,
    ConversionProperties,
    ConvertedDocument,
    ExperimentDocument,
    ExperimentRecord,
    ExperimentSection,
    GraphBatch,
    GraphLabel,
    GraphLink,
    GraphNode,
    GraphRelation,
    NodeKey,
    OfficialDocument,
    Score,
    SourceDocument,
)

from .data import GraphBatchClient, GraphNodesClient
from .data import experiment_mappers as to
from .data.mappers import properties, text

L = GraphLabel


class GraphExperimentStore:
    def __init__(self, client: httpx.Client, path: str) -> None:
        self._batch = GraphBatchClient(client, path)
        self._experiments = GraphNodesClient(client, path, L.EXPERIMENTO)
        self._conversions = GraphNodesClient(client, path, L.EXP_DOCUMENTO)
        self._sections = GraphNodesClient(client, path, L.EXP_SECCION)
        self._chunks = GraphNodesClient(client, path, L.EXP_CHUNK)
        self._scores = GraphNodesClient(client, path, L.EXP_PUNTUACION)
        self._official = GraphNodesClient(client, path, L.JSON)

    def save(self, batch: GraphBatch) -> None:
        self._batch.save(batch)

    def _conversion(self, conversion_id: str) -> ConversionProperties | None:
        raw = self._conversions.properties(conversion_id)
        return to.conversion(raw) if raw is not None else None

    def conversion(self, conversion_id: str) -> ConvertedDocument | None:
        p = self._conversion(conversion_id)
        if p is None or p["estado"] != CONVERTED or not isinstance(p["contenido"], str):
            return None
        try:
            return ConvertedDocument.from_json(p["contenido"])
        except ValueError:
            return None

    def has_conversion(self, conversion_id: str) -> bool:
        p = self._conversion(conversion_id)
        return p is not None and p["estado"] == CONVERTED

    def source(self, conversion_id: str) -> SourceDocument | None:
        raw = self._conversions.properties(conversion_id)
        return to.source(raw) if raw is not None else None

    def content(self, conversion_id: str) -> str | None:
        p = self._conversion(conversion_id)
        return text(p["contenido"]) if p is not None else None

    def conversion_json(self, conversion_id: str) -> str | None:
        p = self._conversion(conversion_id)
        return text(p["conversion"]) if p is not None else None

    def stored_conversion(self, conversion_id: str) -> ConversionProperties | None:
        return self._conversion(conversion_id)

    def official(self, sha256: str) -> OfficialDocument | None:
        return to.official(self._official.get(sha256))

    def official_pages(
        self, per_page: int, first: int = 1, last: int | None = None
    ) -> Iterator[list[OfficialDocument]]:
        for nodes in self._official.pages(per_page, first, last):
            yield [d for node in nodes if (d := to.official(node)) is not None]

    def experiment(self, id: str) -> ExperimentRecord | None:
        p = self._experiments.properties(id)
        return to.record(id, p) if p is not None else None

    def experiments(self) -> list[ExperimentRecord]:
        records = [
            to.record(str(node["id"]), p) for node in self._experiments.all() if (p := properties(node)) is not None
        ]
        return sorted(records, key=lambda r: r.created, reverse=True)

    def documents(self, experiment_id: str) -> list[ExperimentDocument]:
        documents = [
            to.document(target, p) for target, p in self._experiments.outgoing(experiment_id, GraphRelation.EXP_USA)
        ]
        return sorted(documents, key=lambda d: d.origin or d.sha256)

    def sections(self, experiment_id: str, document: ExperimentDocument) -> list[ExperimentSection]:
        sections: list[ExperimentSection] = []
        for n in range(document.sections):
            p = self._sections.properties(f"{experiment_id}:{document.sha256}:{n}")
            if p is not None:
                sections.append(to.section(n, p))
        return sections

    def chunks(self, experiment_id: str, document: ExperimentDocument) -> list[tuple[int, ChunkPiece]]:
        found: list[tuple[int, ChunkPiece]] = []
        for section in self.sections(experiment_id, document):
            for k in range(section.chunks):
                p = self._chunks.properties(f"{experiment_id}:{document.sha256}:{section.index}:{k}")
                if p is not None:
                    found.append((section.index, to.piece(p)))
        return found

    def delete(self, id: str) -> bool:
        if self._experiments.properties(id) is None:
            return False
        self.save(GraphBatch([], [], replace_from=NodeKey(L.EXPERIMENTO, id)))  # sections, chunks, scores
        return self._experiments.delete(id)  # and the node (with its EXP_USA; the EXP_DOCUMENTO stay)

    # Scores

    @staticmethod
    def _score_id(experiment_id: str, score_id: str) -> str:
        return f"{experiment_id}:{score_id}"

    def scores(self, experiment_id: str) -> list[Score]:
        found = []
        for target, _ in self._experiments.outgoing(experiment_id, GraphRelation.EXP_TIENE_PUNTUACION):
            p = self._scores.properties(target)
            score = to.score(p) if p is not None else None
            if score is not None:
                found.append(score)
        return sorted(found, key=lambda s: s.created)

    def score(self, experiment_id: str, score_id: str) -> Score | None:
        p = self._scores.properties(self._score_id(experiment_id, score_id))
        return to.score(p) if p is not None else None

    def save_score(self, experiment_id: str, score: Score) -> None:
        key = NodeKey(L.EXP_PUNTUACION, self._score_id(experiment_id, score.id))
        link = GraphLink(GraphRelation.EXP_TIENE_PUNTUACION, NodeKey(L.EXPERIMENTO, experiment_id), key)
        self.save(GraphBatch([GraphNode(key, dict(to.score_properties(experiment_id, score)))], [link]))

    def delete_score(self, experiment_id: str, score_id: str) -> bool:
        return self._scores.delete(self._score_id(experiment_id, score_id))
