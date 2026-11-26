"""describe: what is told of each process."""

from datetime import UTC, datetime, timedelta

from common.processes import ProcessFacts, ProcessState, describe

START = datetime(2026, 11, 6, 10, 0, tzinfo=UTC)


def facts(
    state: ProcessState = ProcessState.RUNNING,
    id: str = "e1",
    started: str | None = START.isoformat(),
    finished: str | None = None,
    phase: str | None = None,
    position: int | None = None,
    done: int = 0,
    total: int = 0,
) -> ProcessFacts:
    return ProcessFacts(
        id,
        "chunking",
        "experiment",
        "n",
        state,
        START.isoformat(),
        started,
        finished,
        phase,
        position,
        ("hybrid",),
        done,
        total,
    )


def test_a_running_process_says_how_far_with_what_and_for_how_long() -> None:
    seen = describe(facts(done=2, total=8), START + timedelta(seconds=30))
    assert (seen.done, seen.total, seen.percent, seen.elapsed_seconds) == (2, 8, 25, 30)
    assert seen.strategies == ("hybrid",) and seen.duration_seconds is None


def test_it_only_says_what_is_left_once_it_is_slow() -> None:
    assert describe(facts(done=2, total=8), START + timedelta(seconds=59)).remaining_seconds is None
    assert describe(facts(done=2, total=8), START + timedelta(seconds=120)).remaining_seconds == 360
    assert describe(facts(done=0, total=8), START + timedelta(seconds=300)).remaining_seconds is None


def test_an_ended_process_only_says_when_and_how_long() -> None:
    finished = (START + timedelta(minutes=11)).isoformat()
    seen = describe(facts(ProcessState.FINISHED, finished=finished, done=8, total=8), START + timedelta(hours=1))
    assert (seen.started, seen.finished, seen.duration_seconds) == (START.isoformat(), finished, 660)
    assert seen.done is None and seen.percent is None and seen.strategies is None and seen.elapsed_seconds is None


def test_a_queued_process_says_its_place_and_no_times() -> None:
    seen = describe(facts(ProcessState.QUEUED, started=None, position=2), START)
    assert seen.position == 2 and seen.started is None and seen.elapsed_seconds is None


def test_times_with_and_without_offset_are_both_understood() -> None:
    naive = datetime.now().replace(microsecond=0)
    aware = naive.astimezone() + timedelta(seconds=5)
    seen = describe(facts(started=naive.isoformat(), total=1), aware)
    assert seen.elapsed_seconds == 5
