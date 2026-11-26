"""The ports of embeddings over data: the chunks it reads, the vectors it writes, its active configuration and the
record of its runs.

Reading a document's chunks walks data's relationships (data has no deep read): JSON → SECCION → FRAGMENTOS is
1 + 2 per section + 1 per chunk requests, all to this same server. Enough for today's corpus; if it weighs, the
improvement goes in data (a route that follows the composition relationships from a node), not here.
"""

from collections import Counter
from collections.abc import Mapping

from common.clock import now
from common.http import Json
from embeddings.config import ACTIVE_CONFIG_ID
from embeddings.models import (
    ConfigProperties,
    EmbeddableChunk,
    EmbeddableDocument,
    EmbeddingConfig,
    GraphBatch,
    GraphLabel,
    GraphLink,
    GraphNode,
    GraphRelation,
    NodeKey,
    RunKind,
    RunProperties,
    VectorIndexSpec,
)

from . import mappers as to
from .client import DataClient

L, R = GraphLabel, GraphRelation
VECTOR = ("embedding",)  # every vector (data reads it as all of embedding_*): ~8 KB of JSON nobody reads back
FILE = ("contenido",)  # the RAW's file (base64): only its name is read
PARSED = ("documento",)  # the JSON's whole parsed document (feature 042): not needed to embed
_RECORD = {RunKind.RUN: L.CORRIDA_EMBEDDINGS, RunKind.EXPERIMENT: L.EXP_EMBEDDINGS}

type Ordered = tuple[int, int, EmbeddableChunk]  # (section order, chunk index, chunk)


def _order(raw: Mapping[str, Json], key: str) -> int:
    return to.integer(raw, key) or 0


class HttpChunkSource:
    def __init__(self, data: DataClient) -> None:
        self._data = data

    def document(self, sha256: str) -> EmbeddableDocument | None:
        raw = self._data.node(L.JSON, sha256, PARSED)
        if raw is None:
            return None
        file = self._data.node(L.RAW, sha256, FILE)
        return to.document(sha256, raw, None if file is None else to.text(file, "nombre"))

    def missing(self, property: str, page: int | None, per_page: int | None) -> list[str]:
        return self._data.missing(property, page, per_page)

    def _chunks(self, section: str, order: int, section_label: GraphLabel, chunk_label: GraphLabel) -> list[Ordered]:
        relation = R.TIENE_FRAGMENTO if chunk_label is L.FRAGMENTOS else R.EXP_TIENE_CHUNK
        found: list[Ordered] = []
        for id in self._data.outgoing(section_label, section, relation):
            raw = self._data.node(chunk_label, id, VECTOR)
            if raw is not None:
                found.append((order, _order(raw, "indice"), to.chunk(id, raw)))
        return found

    def chunks(self, sha256: str) -> list[EmbeddableChunk]:
        found: list[Ordered] = []
        for section in self._data.outgoing(L.JSON, sha256, R.TIENE_SECCION):
            raw = self._data.node(L.SECCION, section)
            if raw is not None:
                found += self._chunks(section, _order(raw, "orden"), L.SECCION, L.FRAGMENTOS)
        return [c for _, _, c in sorted(found, key=lambda item: item[:2])]

    def experiment_status(self, experiment: str) -> str | None:
        raw = self._data.node(L.EXPERIMENTO, experiment, ("progreso", "resultados", "documentos", "chunking"))
        return None if raw is None else to.text(raw, "estado") or "unknown"

    def experiment_documents(self, experiment: str) -> list[str]:
        """From the ids of its EXP_DOCUMENTO (<experiment>:<sha256>, feature 055 part b): one request."""
        found = self._data.outgoing(L.EXPERIMENTO, experiment, R.EXP_TIENE_DOCUMENTO)
        return sorted({id.rsplit(":", 1)[-1] for id in found})

    def experiment_missing(self, embeddings_experiment: str) -> list[str] | None:
        return self._data.experiment_missing(embeddings_experiment)

    def experiment_document_chunks(self, experiment: str, sha256: str) -> list[EmbeddableChunk]:
        """EXP_DOCUMENTO → EXP_SECCION → EXP_CHUNK: one request more than JSON → SECCION → FRAGMENTOS."""
        found: list[Ordered] = []
        for section in self._data.outgoing(L.EXP_DOCUMENTO, f"{experiment}:{sha256}", R.EXP_TIENE_SECCION):
            raw = self._data.node(L.EXP_SECCION, section)
            if raw is not None:
                found += self._chunks(section, _order(raw, "orden"), L.EXP_SECCION, L.EXP_CHUNK)
        return [c for _, _, c in sorted(found, key=lambda item: item[:2])]

    def _parsed(self) -> list[tuple[str, Mapping[str, Json]]]:
        return list(self._data.nodes(L.JSON, PARSED))

    def fingerprint_counts(self) -> dict[str, int]:
        """Every official JSON, a page at a time, without its parsed document."""
        return dict(Counter(key for _, raw in self._parsed() for key in to.fingerprints(raw)))

    def with_fingerprint(self, key: str) -> list[str]:
        return [sha256 for sha256, raw in self._parsed() if key in to.fingerprints(raw)]


class HttpVectorStore:
    """VectorSink: the indexes and the vectors, in data."""

    def __init__(self, data: DataClient) -> None:
        self._data = data

    def ensure_index(self, index: VectorIndexSpec) -> None:
        self._data.ensure_index(index)

    def save(self, batch: GraphBatch) -> None:
        self._data.save(batch)

    def drop_index(self, name: str, drop_property: bool) -> bool:
        return self._data.drop_index(name, drop_property)


class GraphConfigStore:
    """ConfigStore: the active configuration, this module's CONFIG_OFICIAL node."""

    def __init__(self, data: DataClient) -> None:
        self._data = data

    def active(self) -> EmbeddingConfig | None:
        raw = self._data.node(L.CONFIG_OFICIAL, ACTIVE_CONFIG_ID)
        return None if raw is None else to.config(raw)

    def set(self, config: EmbeddingConfig) -> None:
        properties: ConfigProperties = {
            "modulo": "embeddings",
            "modelo": config.model,
            "max_tokens": config.max_tokens,
            "origen": config.origin.value,
            "experimento": config.experiment,
            "modificado_en": config.modified or now(),
        }
        self._data.save(GraphBatch([GraphNode(NodeKey(L.CONFIG_OFICIAL, ACTIVE_CONFIG_ID), properties)]))

    def clear(self) -> bool:
        return self._data.delete(L.CONFIG_OFICIAL, ACTIVE_CONFIG_ID)


class GraphRunStore:
    """Each run is a CORRIDA_EMBEDDINGS node and each experiment an EXP_EMBEDDINGS one, written again (merge) whenever
    it changes."""

    def __init__(self, data: DataClient) -> None:
        self._data = data

    def save(self, kind: RunKind, id: str, status: str, requested: str, detail: str) -> None:
        properties: RunProperties = {"estado": status, "inicio": requested, "detalle": detail}
        self._data.save(GraphBatch([GraphNode(NodeKey(_RECORD[kind], id), properties)]))

    def link(self, id: str, chunking_experiment: str) -> None:
        link = GraphLink(R.EXP_USA, NodeKey(L.EXP_EMBEDDINGS, id), NodeKey(L.EXPERIMENTO, chunking_experiment))
        self._data.save(GraphBatch([], [link]))

    def linked_by(self, id: str) -> list[str]:
        return self._data.incoming(L.EXP_EMBEDDINGS, id, R.PIPE_USA)

    def details(self, kind: RunKind) -> list[str]:
        found = (to.text(raw, "detalle") for _, raw in self._data.nodes(_RECORD[kind]))
        return [detail for detail in found if detail is not None]

    def detail(self, kind: RunKind, id: str) -> str | None:
        raw = self._data.node(_RECORD[kind], id)
        return None if raw is None else to.text(raw, "detalle")

    def delete(self, kind: RunKind, id: str) -> bool:
        return self._data.delete(_RECORD[kind], id)
