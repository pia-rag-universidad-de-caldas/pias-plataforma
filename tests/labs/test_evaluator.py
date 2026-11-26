"""The lab actor evaluates stored chunks and reads them through data's public graph API."""

import httpx
import pytest

from labs.lab2 import evaluator
from labs.lab2.evaluator import evaluate_document, get_experiment_chunks


def test_a_good_chunk_meets_the_acceptance_threshold() -> None:
    result = evaluate_document([{"id": "e:sha:0", "texto_contextualizado": "contenido", "tokens": 4}], 126)

    assert result["accepted"] is True
    assert result["score"] == 5.0
    chunk_results = result["chunk_results"]
    assert isinstance(chunk_results, list) and chunk_results[0]["score"] == 5.0


def test_duplicate_chunks_are_scored_and_rejected() -> None:
    chunks = [
        {"id": "e:sha:0", "texto_contextualizado": "Contenido", "tokens": 4},
        {"id": "e:sha:1", "texto_contextualizado": " contenido ", "tokens": 4},
    ]

    result = evaluate_document(chunks, 126)

    assert result["accepted"] is False
    duplicate_summary = result["chunk_duplicated"]
    chunk_results = result["chunk_results"]
    assert isinstance(duplicate_summary, dict)
    assert isinstance(chunk_results, list)
    assert duplicate_summary["duplicate_ratio"] == 0.5
    assert [chunk["score"] for chunk in chunk_results] == [5.0, 0.0]


def test_experiment_chunks_are_loaded_from_data_relationships() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/nodes/EXPERIMENTO/exp-1/relationships"):
            return httpx.Response(
                200,
                json=[
                    {
                        "type": "EXP_GENERA",
                        "source": {"label": "EXPERIMENTO", "id": "exp-1"},
                        "target": {"label": "EXP_SECCION", "id": "exp-1:doc:s0"},
                    }
                ],
            )
        if request.url.path.endswith("/nodes/EXP_SECCION/exp-1:doc:s0/relationships"):
            return httpx.Response(
                200,
                json=[
                    {
                        "type": "EXP_TIENE_CHUNK",
                        "source": {"label": "EXP_SECCION", "id": "exp-1:doc:s0"},
                        "target": {"label": "EXP_CHUNK", "id": "exp-1:doc:0"},
                    }
                ],
            )
        if request.url.path.endswith("/nodes/EXP_CHUNK/exp-1:doc:0"):
            return httpx.Response(
                200,
                json={
                    "label": "EXP_CHUNK",
                    "id": "exp-1:doc:0",
                    "properties": {"indice": 0, "texto_contextualizado": "texto", "tokens": 2},
                },
            )
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(respond))
    try:
        chunks = get_experiment_chunks("exp-1", base_url="http://test", client=client)
    finally:
        client.close()

    assert chunks == [{"id": "exp-1:doc:0", "indice": 0, "texto_contextualizado": "texto", "tokens": 2}]


def test_a_pipeline_review_posts_the_score_to_its_answer_route(monkeypatch: pytest.MonkeyPatch) -> None:
    original_client = httpx.Client
    seen: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/pipeline/runs/run-1":
            return httpx.Response(
                200,
                json={
                    "iterations": [
                        {
                            "stage": "laboratorio",
                            "index": 1,
                            "config": {"chunking": {"chunker": "hybrid", "max_tokens": 126}},
                        }
                    ]
                },
            )
        if request.method == "GET" and request.url.path.endswith("/nodes/EXPERIMENTO/exp-1/relationships"):
            return httpx.Response(
                200,
                json=[
                    {
                        "type": "EXP_GENERA",
                        "source": {"label": "EXPERIMENTO", "id": "exp-1"},
                        "target": {"label": "EXP_SECCION", "id": "exp-1:doc:s0"},
                    }
                ],
            )
        if request.method == "GET" and request.url.path.endswith("/nodes/EXP_SECCION/exp-1:doc:s0/relationships"):
            return httpx.Response(
                200,
                json=[
                    {
                        "type": "EXP_TIENE_CHUNK",
                        "source": {"label": "EXP_SECCION", "id": "exp-1:doc:s0"},
                        "target": {"label": "EXP_CHUNK", "id": "exp-1:doc:0"},
                    }
                ],
            )
        if request.method == "GET" and request.url.path.endswith("/nodes/EXP_CHUNK/exp-1:doc:0"):
            return httpx.Response(
                200,
                json={
                    "label": "EXP_CHUNK",
                    "id": "exp-1:doc:0",
                    "properties": {"indice": 0, "texto_contextualizado": "texto", "tokens": 2},
                },
            )
        if request.method == "POST" and request.url.path == "/pipeline/runs/run-1/stages/laboratorio/decision":
            seen.append(request.read().decode())
            return httpx.Response(200, json={"status": "running"})
        return httpx.Response(404)

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    result = evaluator.process_inbox_item(
        {
            "run": "run-1",
            "stage": "laboratorio",
            "actor": "lab",
            "iteration": 1,
            "experiment": "exp-1",
            "answer": "/pipeline/runs/run-1/stages/laboratorio/decision",
        },
        base_url="http://test",
    )

    assert result["decision"] == "approve"
    assert '"decision":"approve"' in seen[0]
    assert '"score":5.0' in seen[0]
