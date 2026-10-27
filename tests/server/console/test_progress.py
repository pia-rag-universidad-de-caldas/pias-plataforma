"""A launched run is followed until it ends or waits for an actor (feature 035)."""

from server.console.catalog import Field, Module, Operation
from server.console.progress import bar, snapshot, watch_path


def operation(module: str, method: str, path: str) -> Operation:
    fields = (Field("id", "path", "text", required=True),) if "{id}" in path else ()
    return Operation(Module(module, f"/{module}"), method, path, "", "", fields, None)


def test_which_operations_start_a_run_and_where_it_is_read() -> None:
    assert watch_path(operation("chunking", "POST", "/runs"), "r1", {}) == "/chunking/runs/r1"
    decision = operation("pipeline", "POST", "/runs/{id}/stages/{stage}/decision")
    assert watch_path(decision, None, {"id": "p7"}) == "/pipeline/runs/p7"
    assert watch_path(operation("ingesta", "POST", "/runs"), None, {}) is None  # simulated: no id
    assert watch_path(operation("ingesta", "GET", "/runs"), "x", {}) is None


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


def test_a_chunking_run_counts_what_is_left() -> None:
    now = snapshot({"status": "finished", "progress": {"pending": 0, "chunked": 3, "skipped": 1, "errors": 0}})
    assert now.ended and now.fraction == 1.0 and ("fragmentados", "3") in now.counters


def test_a_pipeline_waiting_for_an_actor_stops_following() -> None:
    now = snapshot({"status": "waiting", "stage": "conversion", "waiting": {"actor": "lab"}})
    assert now.ended and not now.failed and now.note == "etapa: conversion · espera a lab"
    assert snapshot(None).status == "?"


def test_bar() -> None:
    assert bar(0.5, 4) == "██░░  50%"
