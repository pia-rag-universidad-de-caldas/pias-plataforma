"""What chunking's batches really do to a graph (feature 043): through POST /batch of `data` into a real Neo4j (omitted
without one). The JSON is parsing's: chunking must never lose its properties, and an experiment never touches it."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from chunking.adapters.data.mappers import batch_body
from chunking.domain import ExperimentGraph, OfficialGraph, Parameters
from chunking.models import (
    Chunk,
    ExperimentRequest,
    GraphBatch,
    GraphLabel,
    GraphNode,
    NodeKey,
    NodeWrite,
    RequestedChunking,
)
from data.api import ApiSettings, create_app
from data.models import GraphAdapter, GraphRow, Label
from data.repository import PiaaRepository

pytestmark = [pytest.mark.neo4j, pytest.mark.integration]

PARAMETERS = Parameters.resolve(RequestedChunking(), "2")
type Save = Callable[[GraphBatch], None]


def chunk(index: int, heading: str = "Objetivo") -> Chunk:
    return Chunk(index, f"texto {index}", f"{heading}\ntexto {index}", [heading], [1], 3)


def parsed(sha256: str) -> GraphBatch:
    """The JSON as parsing leaves it (feature 042)."""
    properties = {"sha256": sha256, "estado": "parseado", "fingerprint_parseo": "p1", "documento": "x"}
    return GraphBatch([GraphNode(NodeKey(GraphLabel.JSON, sha256), properties, NodeWrite.REPLACE)], [])


@pytest.fixture
def save(real_graph: GraphAdapter) -> Save:
    client = TestClient(create_app(ApiSettings("neo4j://x", "neo4j", None), real_graph))

    def write(batch: GraphBatch) -> None:
        answer = client.post("/batch", json=batch_body(batch))
        assert answer.status_code == 200, answer.text

    return write


def chunks_of(graph: GraphAdapter, sha256: str) -> list[GraphRow]:
    return graph.read(
        "MATCH (:JSON {id: $id})-[:TIENE_SECCION]->(:SECCION)-[:TIENE_FRAGMENTO]->(f:FRAGMENTOS) "
        "RETURN f.indice AS indice ORDER BY indice",
        {"id": sha256},
    )


def json_properties(graph: GraphAdapter, sha256: str) -> dict[str, object]:
    found = PiaaRepository(graph).node(Label.JSON, sha256)
    assert found is not None
    return dict(found.properties)


def test_chunking_again_replaces_the_chunks_and_keeps_the_parse(
    real_graph: GraphAdapter, save: Save, test_prefix: str
) -> None:
    save(parsed(test_prefix))
    save(OfficialGraph.chunked(test_prefix, [chunk(0), chunk(1), chunk(2, "Otro")], PARAMETERS, "p1", "t1", None))
    save(OfficialGraph.chunked(test_prefix, [chunk(0)], PARAMETERS, "p1", "t2", "e1"))
    assert [row["indice"] for row in chunks_of(real_graph, test_prefix)] == [0]
    properties = json_properties(real_graph, test_prefix)
    assert (properties["documento"], properties["fragmentos"], properties["experimento_config"]) == ("x", 1, "e1")


def test_a_failure_keeps_the_chunks(real_graph: GraphAdapter, save: Save, test_prefix: str) -> None:
    save(parsed(test_prefix))
    save(OfficialGraph.chunked(test_prefix, [chunk(0), chunk(1)], PARAMETERS, "p1", "t1", None))
    save(OfficialGraph.failed(test_prefix, "boom", had_chunks=True))
    properties = json_properties(real_graph, test_prefix)
    assert (properties["estado_chunking"], properties["error_chunking"]) == ("fragmentado", "boom")
    assert len(chunks_of(real_graph, test_prefix)) == 2


def test_deleting_an_experiment_leaves_the_json(real_graph: GraphAdapter, save: Save, test_prefix: str) -> None:
    experiment = f"{test_prefix}-e"
    save(parsed(test_prefix))
    request = ExperimentRequest(experiment, "", PARAMETERS, [])
    save(ExperimentGraph.experiment(experiment, request, 1, "t1"))
    save(ExperimentGraph.document(experiment, test_prefix, [chunk(0)], None, 0.1))
    save(GraphBatch([], [], replace_from=NodeKey(GraphLabel.EXPERIMENTO, experiment)))
    assert PiaaRepository(real_graph).node(Label.EXP_CHUNK, f"{experiment}:{test_prefix}:0") is None
    assert json_properties(real_graph, test_prefix)["documento"] == "x"
