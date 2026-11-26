"""History: what is stored of the processes of past sessions, read every few seconds."""

from datetime import UTC, datetime

from common.processes import History, ProcessFacts, ProcessState

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


def test_history_reads_every_few_seconds_and_keeps_the_last_it_knew() -> None:
    now = [0.0]
    answers: list[list[ProcessFacts] | ValueError] = [[facts()], ValueError("down")]

    def read() -> list[ProcessFacts]:
        answer = answers[0]
        if isinstance(answer, ValueError):
            raise answer
        return answer

    history = History(read, (ValueError,), every=5.0, clock=lambda: now[0])
    assert history.current() == ((facts(),), None)
    answers.pop(0)
    assert history.current() == ((facts(),), None)  # not read yet
    now[0] = 6.0
    assert history.current() == ((facts(),), "down")
