"""A process as a card (feature 039): alive, how far; ended, only its times."""

from server.console.bodies import JsonObject
from server.console.live import ProcessFeed, clock, process_card, summary


def test_clock_reads_as_a_person_would() -> None:
    assert (clock(45), clock(200), clock(3900)) == ("45 s", "3 min 20 s", "1 h 05 min")


def test_a_running_card_says_how_far_how_long_and_with_what() -> None:
    process: JsonObject = {"id": "e", "module": "chunking", "kind": "experiment", "phase": "02", "name": "n"}
    process |= {"state": "running", "done": 2, "total": 8, "percent": 25, "elapsed_seconds": 200}
    process |= {"remaining_seconds": 600, "strategies": ["hybrid"]}
    card = process_card(process)
    assert card.title == "chunking · experimento fase 02: n" and card.status is True
    assert card.text == "en curso · 2/8 (25 %) · lleva 3 min 20 s · faltan ~10 min 00 s · con hybrid"


def test_an_ended_card_only_says_its_times() -> None:
    process: JsonObject = {"id": "e", "module": "ingesta", "kind": "ingestion", "name": "x", "state": "finished"}
    process |= {"started": "2026-11-06T10:00:00", "finished": "2026-11-06T10:11:00", "duration_seconds": 660}
    assert process_card(process).text == (
        "terminado · empezó 2026-11-06 10:00:00 · terminó 2026-11-06 10:11:00 · duró 11 min 00 s"
    )


def test_a_queued_card_says_its_place() -> None:
    process: JsonObject = {
        "id": "e",
        "module": "chunking",
        "kind": "run",
        "name": "x",
        "state": "queued",
        "position": 2,
    }
    assert process_card(process).text == "en cola · puesto 2"


def test_the_summary_always_says_the_alive_and_only_the_rest_that_exist() -> None:
    assert summary({"counts": {"running": 1, "queued": 2, "finished": 3, "failed": 0}}) == (
        "1 en curso · 2 en cola · 0 esperando · 3 terminados"
    )


def test_a_server_that_does_not_answer_is_a_problem_not_an_error() -> None:
    feed = ProcessFeed("http://127.0.0.1:1", "/processes/ws", {"phase": "01"})
    assert feed.url == "ws://127.0.0.1:1/processes/ws?phase=01"
    assert feed.read(0.0) is False and "sin conexión" in feed.problem
    assert feed.read(1.0) is False  # it doesn't try again at once
