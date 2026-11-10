"""The board: how many processes there are in each state, and each one in the order it is shown."""

from collections.abc import Iterable, Sequence
from datetime import datetime

from .models import ENDED, Process, ProcessBoard, ProcessSnapshot, ProcessState

MAX_ENDED = 50  # ended processes listed by a board (all of them count)
_ORDER = {ProcessState.RUNNING: 0, ProcessState.WAITING: 1, ProcessState.QUEUED: 2}


def _ended_first(process: Process) -> str:
    return process.finished or process.started or ""


def board(
    snapshots: Iterable[ProcessSnapshot],
    at: datetime,
    phase: str | None = None,
    states: Sequence[ProcessState] = (),
) -> ProcessBoard:
    """The snapshots gathered, only those of `phase` and of `states` if they are given."""
    gathered = list(snapshots)
    found = [
        p
        for snapshot in gathered
        for p in snapshot.processes
        if (phase is None or p.phase == phase) and (not states or p.state in states)
    ]
    counts = {state: sum(1 for p in found if p.state is state) for state in ProcessState}
    alive = sorted((p for p in found if p.state not in ENDED), key=lambda p: (_ORDER[p.state], p.position or 0))
    ended = sorted((p for p in found if p.state in ENDED), key=_ended_first, reverse=True)
    problems = tuple(s.problem for s in gathered if s.problem)
    return ProcessBoard(at.isoformat(timespec="seconds"), counts, (*alive, *ended[:MAX_ENDED]), problems)
