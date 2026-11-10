"""ConfigStore over data: the active configuration is this module's CONFIG_OFICIAL node (id `llm`)."""

from llm.config import ACTIVE_CONFIG_ID
from llm.models import GraphBatch, GraphLabel, GraphNode, LlmConfig, NodeKey

from . import mappers as to
from .client import DataClient

KEY = NodeKey(GraphLabel.CONFIG_OFICIAL, ACTIVE_CONFIG_ID)


class GraphConfigStore:
    def __init__(self, data: DataClient) -> None:
        self._data = data

    def active(self) -> LlmConfig | None:
        raw = self._data.node(KEY.label, KEY.id)
        return None if raw is None else to.config(raw)

    def set(self, config: LlmConfig) -> None:
        self._data.save(GraphBatch([GraphNode(KEY, to.config_properties(config))]))

    def clear(self) -> bool:
        return self._data.delete(KEY.label, KEY.id)
