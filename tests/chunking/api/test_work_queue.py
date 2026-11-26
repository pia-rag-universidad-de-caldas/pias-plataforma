"""What chunking runs goes in line (feature 039): one at a time, in order, and what waits can leave."""

import threading

import pytest
from fastapi.testclient import TestClient

from chunking.api import ApiSettings, create_app
from chunking.api.work_queue import WorkQueue


def test_jobs_run_one_at_a_time_in_order_and_what_waits_can_leave() -> None:
    queue = WorkQueue()
    release = threading.Event()
    ended = threading.Event()
    done: list[str] = []
    started = threading.Event()

    def first() -> None:
        started.set()
        release.wait(5)
        done.append("a")

    queue.submit("a", first)
    assert started.wait(5) and queue.active == "a" and queue.busy
    queue.submit("b", lambda: done.append("b"))
    queue.submit("c", lambda: done.append("c"))

    def last() -> None:
        done.append("d")
        ended.set()

    queue.submit("d", last)
    assert queue.waiting() == ("b", "c", "d")
    assert queue.cancel("c") and not queue.cancel("c") and not queue.cancel("a")
    release.set()
    assert ended.wait(5)
    assert done == ["a", "b", "d"]


def test_a_job_that_breaks_does_not_stop_the_line() -> None:
    queue = WorkQueue()
    ended = threading.Event()

    def broken() -> None:
        raise ValueError("bug")

    queue.submit("a", broken)
    queue.submit("b", ended.set)
    assert ended.wait(5)


def waiting_queue(limit: int) -> tuple[WorkQueue, threading.Event]:
    """A queue with one job running until the event is set, and nothing waiting."""
    queue = WorkQueue(limit)
    release, started = threading.Event(), threading.Event()

    def running() -> None:
        started.set()
        release.wait(5)

    queue.submit("running", running)
    assert started.wait(5)
    return queue, release


def test_a_queue_with_room_is_not_full() -> None:
    queue, release = waiting_queue(2)
    queue.submit("a", lambda: None)
    assert not queue.full
    release.set()


def test_a_queue_at_its_limit_is_full() -> None:
    queue, release = waiting_queue(1)
    queue.submit("a", lambda: None)
    assert queue.full
    release.set()


def test_leaving_the_line_makes_room() -> None:
    queue, release = waiting_queue(1)
    queue.submit("a", lambda: None)
    queue.cancel("a")
    assert not queue.full
    release.set()


@pytest.fixture
def full_chunking() -> TestClient:
    app = create_app(ApiSettings("http://127.0.0.1:1"))
    app.state.queue = WorkQueue(0)
    return TestClient(app)


def test_a_new_run_is_409_when_the_line_is_full(full_chunking: TestClient) -> None:
    answer = full_chunking.post("/runs", json={"sha256s": ["ab" * 32]})
    assert answer.status_code == 409 and "line" in answer.json()["detail"]


def test_a_new_experiment_is_409_when_the_line_is_full(full_chunking: TestClient) -> None:
    body = {"name": "x", "sha256s": ["ab" * 32]}
    answer = full_chunking.post("/experiments", json=body)
    assert answer.status_code == 409 and "line" in answer.json()["detail"]
