"""What consultas reads to say where a question can be asked (feature 060), over httpx.MockTransport: embeddings'
models and experiments, data's progress and the chunking experiments (EXPERIMENTO nodes in data)."""

import json

import httpx
import pytest

from consultas.adapters import DataClient, EmbeddingsClient
from consultas.models import ChunkingExperiment, Coverage, DataDown, EmbeddingModel, EmbeddingsDown


def http(status: int, body: object) -> httpx.Client:
    return httpx.Client(
        base_url="http://server", transport=httpx.MockTransport(lambda _: httpx.Response(status, json=body))
    )


def test_embeddings_models_are_read_with_their_vector_property() -> None:
    body = [{"name": "m", "dimensions": 384, "default": True, "vector_property": "embedding_m_384"}]
    assert EmbeddingsClient(http(200, body), "/embeddings").models() == [EmbeddingModel("m", 384, "embedding_m_384")]


def test_a_model_without_its_vector_property_is_embeddings_fault() -> None:
    with pytest.raises(EmbeddingsDown):
        EmbeddingsClient(http(200, [{"name": "m", "dimensions": 384}]), "/embeddings").models()


@pytest.mark.parametrize(
    ("row", "model", "dimensions"),
    [
        ({"config": {"model": "m", "max_tokens": 128}}, "m", None),
        ({"model": "e5", "dimensions": 768, "config": {"model": "e5"}}, "e5", 768),
    ],
    ids=["before 059", "059"],
)
def test_an_embeddings_experiment_is_read_with_or_without_the_fields_of_059(
    row: dict[str, object], model: str, dimensions: int | None
) -> None:
    body = [{"id": "x", "status": "finished", "name": "n", "chunking_experiment": "c", "embedded": ["a"], **row}]
    [found] = EmbeddingsClient(http(200, body), "/embeddings").experiments()
    assert (found.model, found.dimensions, found.documents, found.chunking_experiment) == (model, dimensions, 1, "c")


def test_the_active_embeddings_model_is_its_configuration() -> None:
    assert EmbeddingsClient(http(200, {"model": "m", "max_tokens": 128}), "/embeddings").active_model() == "m"


def test_coverage_reads_done_and_total() -> None:
    body = {"total": 10, "done": 4, "missing": 6, "page": 1}
    assert DataClient(http(200, body), "/data").coverage("embedding_m_384") == Coverage(4, 10)


def test_coverage_without_the_route_is_data_down() -> None:
    with pytest.raises(DataDown):
        DataClient(http(404, {"detail": "Not Found"}), "/data").coverage("embedding_m_384")


def test_a_chunking_experiment_is_read_from_its_node_in_data() -> None:
    parameters = json.dumps({"chunker": "page", "tokenizer": "t", "max_tokens": None})
    body = {"label": "EXPERIMENTO", "id": "c", "properties": {"nombre": "page", "chunking": parameters}}
    found = DataClient(http(200, body), "/data").experiment("c")
    assert found == ChunkingExperiment("c", "page", "page", "t", None)


def test_a_chunking_experiment_with_unreadable_parameters_keeps_its_name() -> None:
    body = {"label": "EXPERIMENTO", "id": "c", "properties": {"nombre": "x", "chunking": "{not json"}}
    assert DataClient(http(200, body), "/data").experiment("c") == ChunkingExperiment("c", "x", None, None, None)


def test_a_deleted_chunking_experiment_is_none() -> None:
    assert DataClient(http(404, {"detail": "no node"}), "/data").experiment("c") is None


def test_a_chunking_experiment_is_never_asked_to_chunking() -> None:
    seen: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(404, json={"detail": "no node"})

    DataClient(httpx.Client(base_url="http://test", transport=httpx.MockTransport(answer)), "/data").experiment("c")
    assert seen == ["/data/nodes/EXPERIMENTO/c"]
