"""A process as anybody watching it sees it. While it is alive it tells how far it is and with what; once it ended, only
when it started, when it ended and how long it took."""

from dataclasses import replace
from datetime import datetime

from .models import ENDED, Process, ProcessFacts, ProcessState

SLOW_AFTER = 60.0  # seconds: a process that takes longer starts telling how much it has left


def seconds_between(start: str, end: datetime) -> float | None:
    """From an ISO time (with or without an offset: without one it is local) to `end`; None if it isn't a time."""
    try:
        return end.timestamp() - datetime.fromisoformat(start).timestamp()
    except ValueError:
        return None


def _remaining(elapsed: float, done: int, total: int) -> int | None:
    if elapsed < SLOW_AFTER or done <= 0 or total <= 0:
        return None
    return round(elapsed / done * max(total - done, 0))


def _ended(facts: ProcessFacts) -> Process:
    duration = None
    if facts.started and facts.finished:
        seconds = seconds_between(facts.started, datetime.fromisoformat(facts.finished))
        duration = None if seconds is None else max(round(seconds), 0)
    return Process(
        facts.id,
        facts.module,
        facts.kind,
        facts.name,
        facts.state,
        phase=facts.phase,
        started=facts.started,
        finished=facts.finished,
        duration_seconds=duration,
        error=facts.error,
    )


def describe(facts: ProcessFacts, at: datetime) -> Process:
    """What to tell of a process at that moment: see the module's docstring."""
    if facts.state in ENDED:
        return _ended(facts)
    common = Process(
        facts.id,
        facts.module,
        facts.kind,
        facts.name,
        facts.state,
        phase=facts.phase,
        strategies=facts.strategies or None,
        detail=facts.detail,
    )
    if facts.state is ProcessState.QUEUED:
        return replace(common, position=facts.position)
    elapsed = seconds_between(facts.started, at) if facts.started else None
    elapsed = max(elapsed, 0.0) if elapsed is not None else None
    tracked = facts.total > 0
    counting = elapsed is not None and facts.state is ProcessState.RUNNING
    return replace(
        common,
        started=facts.started,
        done=facts.done if tracked else None,
        total=facts.total if tracked else None,
        percent=min(facts.done * 100 // facts.total, 100) if tracked else None,
        counters=facts.counters or None,
        elapsed_seconds=None if elapsed is None else round(elapsed),
        remaining_seconds=_remaining(elapsed or 0.0, facts.done, facts.total) if counting else None,
    )
