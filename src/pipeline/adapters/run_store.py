"""GraphRunStore: templates and runs in the graph, through data (feature 028).

    (:PIPE_CORRIDA)-[:PIPE_DE]->(:PIPELINE)
    (:PIPE_CORRIDA)-[:PIPE_TIENE_ITERACION]->(:PIPE_ITERACION)-[:PIPE_USA]->(:EXPERIMENTO)
    (:PIPE_CORRIDA)-[:PIPE_TIENE_EVENTO]->(:PIPE_EVENTO)

A run is read back from its PIPE_CORRIDA alone (iterations and events go inside it as JSON); the PIPE_ITERACION and
PIPE_EVENTO nodes are written with it, in the same batch, so the graph can be queried. Every save is one
POST /data/batch: all or nothing.
"""

from collections.abc import Iterator, Mapping

import httpx

from pipeline.config import GRAPH_PAGE_SIZE
from pipeline.models import PipelineRun, RejectedError, RunStore, Template, UnavailableError

from .http import BaseHttpClient, Json, segment
from .mappers import (
    event_id,
    event_properties,
    iteration_id,
    iteration_properties,
    run_from,
    run_properties,
    template_from,
    template_properties,
)

TEMPLATE = "PIPELINE"
RUN = "PIPE_CORRIDA"
ITERATION = "PIPE_ITERACION"
EVENT = "PIPE_EVENTO"
EXPERIMENT = "EXPERIMENTO"


def _ref(label: str, id: str) -> dict[str, str]:
    return {"label": label, "id": id}


def _link(type: str, source: dict[str, str], target: dict[str, str]) -> dict[str, object]:
    return {"type": type, "source": source, "target": target, "properties": {}}


class GraphRunStore(BaseHttpClient, RunStore):
    def __init__(self, client: httpx.Client, path: str) -> None:
        super().__init__(client, path, "data")

    def _nodes(self, label: str) -> Iterator[tuple[str, Mapping[str, Json]]]:
        """(id, properties) of every node of the label, a page at a time."""
        page, pages = 1, 1
        while page <= pages:
            body = self._object(
                self._get(f"/nodes/{label}", (("page", page), ("per_page", GRAPH_PAGE_SIZE))), f"page of {label}"
            )
            try:
                pages = int(body["pages"])
                nodes = list(body["nodes"])
            except (KeyError, TypeError, ValueError) as e:
                raise UnavailableError(f"data answered a page of {label} without nodes/pages: {e}") from e
            for node in nodes:
                yield str(node["id"]), node.get("properties") or {}
            page += 1

    def _node(self, label: str, id: str) -> Mapping[str, Json] | None:
        found = self._get(f"/nodes/{label}/{segment(id)}")
        if found is None:
            return None
        properties = self._object(found, f"{label} node").get("properties") or {}
        return self._object(properties, f"properties of {label} {id}")

    def _batch(self, body: dict[str, object]) -> None:
        if self._request("POST", "/batch", body=body) is None:
            raise RejectedError(f"data has no {self._path}/batch route")

    def templates(self) -> list[Template]:
        return [template_from(id, properties) for id, properties in self._nodes(TEMPLATE)]

    def template(self, id: str) -> Template | None:
        properties = self._node(TEMPLATE, id)
        return None if properties is None else template_from(id, properties)

    def save_template(self, template: Template) -> None:
        node = {"label": TEMPLATE, "id": template.id, "properties": template_properties(template), "mode": "replace"}
        self._batch({"nodes": [node]})

    def delete_template(self, id: str) -> bool:
        return self._request("DELETE", f"/nodes/{TEMPLATE}/{segment(id)}") is not None

    def runs(self) -> list[PipelineRun]:
        return [run_from(id, properties) for id, properties in self._nodes(RUN)]

    def run(self, id: str) -> PipelineRun | None:
        properties = self._node(RUN, id)
        return None if properties is None else run_from(id, properties)

    def save_run(self, run: PipelineRun, created: bool = False) -> None:
        source = _ref(RUN, run.id)
        nodes: list[dict[str, object]] = [
            {"label": RUN, "id": run.id, "properties": run_properties(run), "mode": "replace"}
        ]
        links: list[dict[str, object]] = []
        if created:
            links.append(_link("PIPE_DE", source, _ref(TEMPLATE, run.template.id)))
        for iteration in run.iterations:
            id = iteration_id(run, iteration)
            nodes.append(
                {"label": ITERATION, "id": id, "properties": iteration_properties(run, iteration), "mode": "replace"}
            )
            links.append(_link("PIPE_TIENE_ITERACION", source, _ref(ITERATION, id)))
            links += [_link("PIPE_USA", _ref(ITERATION, id), _ref(EXPERIMENT, e)) for e in iteration.experiments]
        for event in run.events:
            id = event_id(run, event)
            nodes.append({"label": EVENT, "id": id, "properties": event_properties(run, event), "mode": "replace"})
            links.append(_link("PIPE_TIENE_EVENTO", source, _ref(EVENT, id)))
        self._batch({"nodes": nodes, "relationships": links})
