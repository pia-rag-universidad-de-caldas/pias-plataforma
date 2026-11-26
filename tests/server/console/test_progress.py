"""A launched run is followed until it ends or waits for an actor (feature 035)."""

from server.console.bodies import JsonObject, JsonValue
from server.console.catalog import Field, Module, Operation
from server.console.progress import bar, snapshot, watch_path


def operation(module: str, method: str, path: str) -> Operation:
    fields = (Field("id", "path", "text", required=True),) if "{id}" in path else ()
    return Operation(Module(module, f"/{module}"), method, path, "", "", fields, None)


def test_which_operations_start_a_run_and_where_it_is_read() -> None:
    assert watch_path(operation("chunking", "POST", "/runs"), "r1", {}) == "/chunking/runs/r1"
    assert watch_path(operation("chunking", "POST", "/runs/{id}/resume"), "r1", {"id": "r1"}) == "/chunking/runs/r1"
    decision = operation("pipeline", "POST", "/runs/{id}/stages/{stage}/decision")
    assert watch_path(decision, None, {"id": "p7"}) == "/pipeline/runs/p7"
    assert watch_path(operation("ingesta", "POST", "/runs"), None, {}) is None  # simulated: no id
    assert watch_path(operation("ingesta", "GET", "/runs"), "x", {}) is None


def test_adding_to_an_experiment_and_resuming_embeddings_are_followed() -> None:
    added = operation("chunking", "POST", "/experiments/{id}/documents")
    assert watch_path(added, None, {"id": "e1"}) == "/chunking/experiments/e1"
    resumed = operation("embeddings", "POST", "/experiments/{id}/resume")
    assert watch_path(resumed, None, {"id": "x1"}) == "/embeddings/experiments/x1"
    run = operation("embeddings", "POST", "/runs/{id}/resume")
    assert watch_path(run, None, {"id": "r1"}) == "/embeddings/runs/r1"


def test_an_ingestion_with_its_bar_and_last_error() -> None:
    now = snapshot(
        {
            "estado": "en_curso",
            "progreso": {"copiados": 5, "total": 20},
            "errores": [{"origen": "2024/a.pdf", "error": "permiso denegado"}],
        }
    )
    assert now.fraction == 0.25 and not now.ended
    assert now.error == "2024/a.pdf: permiso denegado"
    assert ("copiados", "5") in now.counters


def test_a_chunking_run_counts_over_its_documents_and_partial_ends_it() -> None:
    progress: JsonObject = {"pending": 3, "chunked": 1, "skipped": 1, "unparsed": 0, "errors": 0}
    now = snapshot({"status": "running", "sha256s": ["a", "b", "c", "d"], "progress": progress})
    assert not now.ended and now.fraction == 0.5 and ("fragmentados", "1") in now.counters
    assert snapshot({"status": "partial", "sha256s": ["a"], "progress": progress}).ended


def test_a_parsing_run_counts_in_spanish() -> None:
    now = snapshot({"status": "running", "progress": {"total": 4, "done": 1, "parsed": 1, "missing": 0}})
    assert now.fraction == 0.25 and ("parseados", "1") in now.counters and ("sin RAW", "0") in now.counters


def test_an_ended_ingestion_says_what_it_left_in_data() -> None:
    raw: JsonObject = {"subidos": 2, "ya_estaban": 5, "retirados": 0, "fallidos": 1, "aviso": None}
    now = snapshot({"estado": "terminada", "progreso": {}, "resultado": {"en_data": raw}})
    assert now.note == "data: 2 subidos, 5 ya estaban, 0 retirados, 1 fallidos"


def test_an_ingestion_without_data_shows_why() -> None:
    raw: JsonObject = {"subidos": 0, "aviso": "data no responde"}
    assert snapshot({"estado": "terminada", "resultado": {"en_data": raw}}).note == "data: data no responde"


def test_a_pipeline_waiting_for_an_actor_stops_following() -> None:
    now = snapshot({"status": "waiting", "stage": "conversion", "waiting": {"actor": "lab"}})
    assert now.ended and not now.failed and now.note == "etapa: conversion · espera a lab"
    assert snapshot(None).status == "?"


def test_a_pipeline_by_parts_says_its_part_and_fills_by_parts() -> None:
    parts: list[JsonValue] = [{"index": 1, "status": "done"}, {"index": 2, "status": "running"}, {"index": 3}]
    now = snapshot({"status": "running", "stage": "chunkear", "parts": parts})
    assert now.note == "etapa: chunkear · parte 2/3 (1 hechas)" and now.fraction == 1 / 3


def test_a_run_asked_to_stop_says_so_and_cancel_is_followed() -> None:
    now = snapshot({"status": "running", "cancel_requested": True, "progress": {"total": 2, "done": 1}})
    assert now.note == "cancelando: termina el documento actual" and not now.ended
    cancel = operation("embeddings", "POST", "/runs/{id}/cancel")
    assert watch_path(cancel, None, {"id": "v1"}) == "/embeddings/runs/v1"


def test_bar() -> None:
    assert bar(0.5, 4) == "██░░  50%"
