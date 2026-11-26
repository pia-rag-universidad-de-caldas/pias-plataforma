"""board: what is told of all the processes."""

from datetime import UTC, datetime

from common.processes import ProcessFacts, ProcessSnapshot, ProcessState, board, describe

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


def test_the_board_counts_all_filters_and_puts_the_alive_first() -> None:
    running = describe(facts(id="r", phase="01"), START)
    queued = describe(facts(ProcessState.QUEUED, id="q", phase="02", position=1), START)
    ended = describe(facts(ProcessState.FINISHED, id="f", phase="01", finished=START.isoformat()), START)
    found = board([ProcessSnapshot((ended, queued, running), "data down")], START)
    assert [p.id for p in found.processes] == ["r", "q", "f"]
    assert found.counts[ProcessState.QUEUED] == 1 and found.problems == ("data down",)
    only = board([ProcessSnapshot((ended, queued, running))], START, phase="01", states=[ProcessState.RUNNING])
    assert [p.id for p in only.processes] == ["r"]
