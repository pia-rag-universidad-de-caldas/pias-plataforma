"""The ports of parsing over data (feature 042): the RAW it reads, the JSON it writes and the record of its runs."""

from collections.abc import Iterator, Mapping, Sequence

from parsing.config import RAW_PAGE
from parsing.models import (
    GraphBatch,
    GraphLabel,
    GraphNode,
    NodeKey,
    NodeWrite,
    RawFile,
    RawState,
    RunProperties,
    StoredParse,
)

from .data_client import DataClient
from .mappers import raw_file, raw_state, stored_parse

CONTENT = "contenido"  # left out of every read that doesn't need the file


class HttpRawSource:
    def __init__(self, data: DataClient) -> None:
        self._data = data

    def states(self, sha256s: Sequence[str]) -> Mapping[str, RawState]:
        found: dict[str, RawState] = {}
        for sha256 in dict.fromkeys(sha256s):
            raw = self._data.node(GraphLabel.RAW, sha256, (CONTENT,))
            if raw is not None:
                found[sha256] = raw_state(sha256, raw)
        return found

    def all_states(self) -> Iterator[RawState]:
        for sha256, raw in self._data.nodes(GraphLabel.RAW, RAW_PAGE, (CONTENT,)):
            yield raw_state(sha256, raw)

    def get(self, sha256: str) -> RawFile | None:
        raw = self._data.node(GraphLabel.RAW, sha256)
        return raw_file(sha256, raw) if raw is not None else None


class HttpParsedSink:
    def __init__(self, data: DataClient) -> None:
        self._data = data

    def previous(self, sha256: str) -> StoredParse | None:
        raw = self._data.node(GraphLabel.JSON, sha256)
        return stored_parse(raw) if raw is not None else None

    def save(self, batch: GraphBatch) -> None:
        self._data.save(batch)


class GraphRunStore:
    """Each run is a CORRIDA_PARSEO node, written again whenever it changes (merge)."""

    def __init__(self, data: DataClient) -> None:
        self._data = data

    def save(self, id: str, status: str, requested: str, detail: str) -> None:
        properties: RunProperties = {"estado": status, "inicio": requested, "detalle": detail}
        node = GraphNode(NodeKey(GraphLabel.CORRIDA_PARSEO, id), properties, NodeWrite.MERGE)
        self._data.save(GraphBatch([node]))

    def details(self) -> list[str]:
        return [
            str(raw["detalle"]) for _, raw in self._data.nodes(GraphLabel.CORRIDA_PARSEO, RAW_PAGE) if "detalle" in raw
        ]

    def detail(self, id: str) -> str | None:
        raw = self._data.node(GraphLabel.CORRIDA_PARSEO, id)
        found = raw.get("detalle") if raw is not None else None
        return found if isinstance(found, str) else None
