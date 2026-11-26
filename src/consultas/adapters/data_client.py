"""DataClient: the routes of data that consultas uses.

    POST   {data}/vectors/search {index, vector, k, experiment?, sha256s?}   (the closest chunks; 404: no index yet)
    POST   {data}/documents/search {text, k}                      (the documents of the courses a text names, 057)
    GET    {data}/progress/embeddings?property=&per_page=1        (official documents with a model's vectors, 060)
    POST   {data}/batch                                           (a question with its chat and citations, all at once)
    GET    {data}/nodes/{label}?page&per_page                     GET {data}/nodes/{label}/{id}[?omit=...]
    GET    {data}/nodes/{label}/{id}/relationships                DELETE {data}/nodes/{label}/{id}

A 404 is None; another 4xx is Rejected (data refused what consultas sent: 502); data down (network, timeout, 5xx, Neo4j
behind it) is DataDown (503).
"""

from collections.abc import Iterator, Mapping, Sequence

import httpx

from common.http import BaseHttpClient, ErrorPolicy, Json, QueryParams, paginate, segment
from consultas.config import LIST_PAGE
from consultas.models import (
    ChunkingExperiment,
    CourseMatch,
    Coverage,
    DataDown,
    GraphBatch,
    GraphLabel,
    NodeKey,
    Rejected,
    Source,
)

from . import mappers as to

EXPERIMENT_OMIT = (
    "documentos",
    "progreso",
    "resultados",
)  # an EXPERIMENTO's heavy JSON: /targets needs only its name and parameters

DATA_ERRORS = ErrorPolicy("data", DataDown, Rejected)


def _key(key: NodeKey) -> dict[str, str]:
    return {"label": key.label.value, "id": key.id}


def batch_body(batch: GraphBatch) -> dict[str, object]:
    body: dict[str, object] = {
        "nodes": [{**_key(n.key), "properties": dict(n.properties), "mode": n.mode.value} for n in batch.nodes],
        "relationships": [
            {"type": r.type.value, "source": _key(r.source), "target": _key(r.target), "properties": dict(r.properties)}
            for r in batch.links
        ],
    }
    if batch.replace_from is not None:
        body["replace_from"] = _key(batch.replace_from)
    return body


def _omit(omit: Sequence[str]) -> QueryParams | None:
    return tuple(("omit", name) for name in omit) or None


class DataClient(BaseHttpClient):
    """`path`: data's prefix in the server (/data)."""

    def __init__(self, client: httpx.Client, path: str) -> None:
        super().__init__(client, path, DATA_ERRORS)

    def search(
        self,
        index: str,
        vector: list[float],
        k: int,
        experiment: str | None = None,
        sha256s: Sequence[str] | None = None,
    ) -> list[Source]:
        body: dict[str, object] = {"index": index, "vector": vector, "k": k}
        if experiment is not None:
            body["experiment"] = experiment
        if sha256s is not None:
            body["sha256s"] = list(sha256s)
        response = self._request("POST", "/vectors/search", body=body)
        if response is None:  # no index: nothing was embedded with that model yet
            return []
        found = self._json(response)
        if not isinstance(found, list):
            raise DataDown(f"it answered a search that isn't a list: {str(found)[:300]}")
        return [to.source(row, DataDown) for row in found]

    def courses(self, text: str, k: int) -> list[CourseMatch]:
        """POST /documents/search (feature 057); [] from a data without that route (before 057)."""
        response = self._request("POST", "/documents/search", body={"text": text, "k": k})
        if response is None:
            return []
        found = self._json(response)
        if not isinstance(found, list):
            raise DataDown(f"it answered a document search that isn't a list: {str(found)[:300]}")
        return [to.course(row, DataDown) for row in found]

    def coverage(self, vector_property: str) -> Coverage:
        """Only the counts: one sha256 of the page is read."""
        found = self._get("/progress/embeddings", (("property", vector_property), ("per_page", 1)))
        if found is None:
            raise DataDown(f"it has no {self._path}/progress/embeddings route (feature 057)")
        return to.coverage(found, DataDown)

    def save(self, batch: GraphBatch) -> None:
        """All of it or nothing."""
        if self._request("POST", "/batch", body=batch_body(batch)) is None:
            raise DataDown(f"it has no {self._path}/batch route")

    def node(self, label: GraphLabel, id: str, omit: Sequence[str] = ()) -> Mapping[str, Json] | None:
        """The properties of the node; None if there is none."""
        return to.properties(self._get(f"/nodes/{label.value}/{segment(id)}", _omit(omit)))

    def experiment(self, id: str) -> ChunkingExperiment | None:
        """A chunking experiment, from its EXPERIMENTO node (feature 060: the ChunkingCatalog port); None if deleted."""
        found = self.node(GraphLabel.EXPERIMENTO, id, omit=EXPERIMENT_OMIT)
        return None if found is None else to.chunking_experiment(id, found)

    def nodes(self, label: GraphLabel) -> Iterator[tuple[str, Mapping[str, Json]]]:
        """(id, properties) of every node of the label, a page at a time."""

        def page(number: int) -> Json:
            return self._get(f"/nodes/{label.value}", (("page", number), ("per_page", LIST_PAGE)))

        for body in paginate(page, "pages", DataDown):
            for node in body.get("nodes") or []:
                found = to.properties(node)
                if found is not None and "id" in node:
                    yield str(node["id"]), found

    def outgoing(self, label: GraphLabel, id: str, type: str) -> list[tuple[str, str, Mapping[str, Json]]]:
        """(target label, target id, properties) of the relationships of `type` that leave the node; [] without it."""
        found = self._get(f"/nodes/{label.value}/{segment(id)}/relationships") or []
        links: list[tuple[str, str, Mapping[str, Json]]] = []
        for r in found if isinstance(found, list) else []:
            if not isinstance(r, Mapping) or r.get("type") != type:
                continue
            source, target, properties = r.get("source"), r.get("target"), r.get("properties")
            if not isinstance(source, Mapping) or (source.get("label"), source.get("id")) != (label.value, id):
                continue
            if isinstance(target, Mapping) and "id" in target:
                links.append(
                    (
                        str(target.get("label")),
                        str(target["id"]),
                        properties if isinstance(properties, Mapping) else {},
                    )
                )
        return links

    def delete(self, label: GraphLabel, id: str) -> bool:
        return self._request("DELETE", f"/nodes/{label.value}/{segment(id)}") is not None
