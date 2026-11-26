"""The stores of chunking in data (feature 043), over HTTP with GraphBatchClient and one GraphNodesClient per label;
data's JSON becomes chunking models in data/mappers.py.

    POST   {data}/batch                               chunks under a JSON, experiments, the configuration, runs
    GET    {data}/nodes/JSON/{sha256}                 a parsed document (parsing's, feature 042)
    GET    {data}/progress/chunking                   what is missing with a configuration (feature 045), and every
                                                      parsed JSON (?list=all, feature 059)
    GET    {data}/nodes/EXPERIMENTO[/{id}[/relationships]]   (and EXP_DOCUMENTO/{id}: feature 055 part b)
    GET    {data}/nodes/CONFIG_OFICIAL/{id}, {data}/nodes/CORRIDA_CHUNKING[/{id}]
    DELETE {data}/nodes/{EXPERIMENTO|CONFIG_OFICIAL}/{id}
"""

import json
from collections.abc import Mapping

import httpx

from chunking.models import (
    ActiveConfig,
    ChunkingParameters,
    ChunkingRun,
    ConfigProperties,
    DocumentUse,
    ExperimentDependents,
    ExperimentRecord,
    GraphBatch,
    GraphLabel,
    GraphNode,
    GraphRelation,
    NodeKey,
    ParsedDocument,
    fit_json,
)

from . import mappers as to
from .batch_client import GraphBatchClient
from .nodes_client import GraphNodesClient
from .progress_client import GraphProgressClient

L = GraphLabel
CONFIG_ID = "activa"  # the only CONFIG_OFICIAL


class GraphDocumentStore:
    """DocumentStore: the parsed documents, and writing what hangs from them."""

    def __init__(self, client: httpx.Client, path: str) -> None:
        self._batch = GraphBatchClient(client, path)
        self._documents = GraphNodesClient(client, path, L.JSON)
        self._progress = GraphProgressClient(client, path)

    def save(self, batch: GraphBatch) -> None:
        self._batch.save(batch)

    def document(self, sha256: str) -> ParsedDocument | None:
        raw = self._documents.properties(sha256)
        return to.parsed(sha256, raw) if raw is not None else None

    def missing(self, fingerprint: str, page: int | None, per_page: int | None) -> list[str]:
        return self._progress.missing(fingerprint, page, per_page)

    def parsed_documents(self) -> list[str]:
        return self._progress.parsed()

    def parsed_count(self) -> int:
        return self._progress.parsed_count()

    def chunked_with(self) -> list[ChunkingParameters | None]:
        return [
            to.official_parameters(raw) for node in self._documents.all() if (raw := to.properties(node)) is not None
        ]


class GraphExperimentStore(GraphDocumentStore):
    """ExperimentStore: the experiment record, besides the documents."""

    def __init__(self, client: httpx.Client, path: str) -> None:
        super().__init__(client, path)
        self._experiments = GraphNodesClient(client, path, L.EXPERIMENTO)
        self._documents_of = GraphNodesClient(client, path, L.EXP_DOCUMENTO)

    def experiment(self, id: str) -> ExperimentRecord | None:
        p = self._experiments.properties(id)
        return to.record(id, p) if p is not None else None

    def experiments(self) -> list[ExperimentRecord]:
        records = [
            to.record(str(node["id"]), p)
            for node in self._experiments.all()
            if isinstance(node, Mapping) and (p := to.properties(node)) is not None
        ]
        return sorted(records, key=lambda r: r.created, reverse=True)

    def documents(self, experiment_id: str) -> list[str]:
        """From the ids of its EXP_DOCUMENTO (<experiment>:<sha256>), one request (feature 059: an experiment of
        the whole corpus has thousands)."""
        return [
            id.rsplit(":", 1)[-1]
            for id, _ in self._experiments.outgoing(experiment_id, GraphRelation.EXP_TIENE_DOCUMENTO)
        ]

    def uses(self, experiment_id: str) -> list[DocumentUse]:
        """One read per EXP_DOCUMENTO of the experiment (feature 055 part b), in the order data answers them."""
        found: list[DocumentUse] = []
        for id, _ in self._experiments.outgoing(experiment_id, GraphRelation.EXP_TIENE_DOCUMENTO):
            raw = self._documents_of.properties(id)
            if raw is not None:
                found.append(to.use(id.rsplit(":", 1)[-1], raw))
        return found

    def dependents(self, id: str) -> ExperimentDependents:
        """From the relationships of the EXPERIMENTO (read once per type)."""
        return ExperimentDependents(
            embeddings=self._experiments.incoming(id, GraphRelation.EXP_USA),
            pipeline=self._experiments.incoming(id, GraphRelation.PIPE_USA),
        )

    def delete(self, id: str) -> bool:
        if self._experiments.properties(id) is None:
            return False
        # Its documents, sections, chunks and their vectors (composition); the JSON stay (EXP_DE).
        self.save(GraphBatch([], [], replace_from=NodeKey(L.EXPERIMENTO, id)))
        return self._experiments.delete(id)  # and the node


class GraphConfigStore:
    """ConfigStore: the active configuration, one CONFIG_OFICIAL node."""

    def __init__(self, client: httpx.Client, path: str) -> None:
        self._batch = GraphBatchClient(client, path)
        self._configs = GraphNodesClient(client, path, L.CONFIG_OFICIAL)

    def stored(self) -> ActiveConfig | None:
        raw = self._configs.properties(CONFIG_ID)
        return to.config(raw) if raw is not None else None

    def put(self, config: ActiveConfig) -> None:
        asked = config.requested
        properties: ConfigProperties = {
            "chunker": asked.chunker.value if asked.chunker else "hybrid",
            "tokenizador": asked.tokenizer,
            "max_tokens": asked.max_tokens,
            "fusionar_vecinos": asked.merge_peers,
            "fit": json.dumps(fit_json(asked.fit)) if asked.fit else None,
            "origen": config.origin.value,
            "experimento": config.experiment,
            "modificado_en": config.modified or "",
        }
        self._batch.save(GraphBatch([GraphNode(NodeKey(L.CONFIG_OFICIAL, CONFIG_ID), properties)], []))

    def clear(self) -> bool:
        return self._configs.delete(CONFIG_ID)


class GraphRunStore:
    """RunStore: the record of POST /runs, which outlives the server."""

    def __init__(self, client: httpx.Client, path: str) -> None:
        self._batch = GraphBatchClient(client, path)
        self._runs = GraphNodesClient(client, path, L.CORRIDA_CHUNKING)

    def save(self, batch: GraphBatch) -> None:
        self._batch.save(batch)

    def run(self, id: str) -> ChunkingRun | None:
        raw = self._runs.properties(id)
        return to.run(id, raw) if raw is not None else None

    def runs(self) -> list[ChunkingRun]:
        found = [
            read
            for node in self._runs.all()
            if isinstance(node, Mapping)
            and (raw := to.properties(node)) is not None
            and (read := to.run(str(node.get("id")), raw)) is not None
        ]
        return sorted(found, key=lambda r: r.requested, reverse=True)
