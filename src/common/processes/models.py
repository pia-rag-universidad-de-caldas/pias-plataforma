"""What a process is as anybody watching it sees it: its state, its facts, its view and the board that gathers them."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol


class ProcessState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"  # for an actor
    FINISHED = "finished"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"  # the server stopped while it ran


ENDED = frozenset(
    {ProcessState.FINISHED, ProcessState.FAILED, ProcessState.CANCELLED, ProcessState.INTERRUPTED},
)


@dataclass(frozen=True)
class ProcessFacts:
    """What a module knows of one of its processes."""

    id: str
    module: str
    kind: str  # experiment, run, ingestion...
    name: str
    state: ProcessState
    requested: str  # ISO, when it was asked for: a queued one's order
    started: str | None = None  # ISO
    finished: str | None = None  # ISO
    phase: str | None = None  # 01 or 02: only the experiments of chunking
    position: int | None = None  # in its queue, from 1
    strategies: tuple[str, ...] = ()
    done: int = 0
    total: int = 0
    counters: Mapping[str, int] = field(default_factory=dict)
    detail: str | None = None  # the stage, or what it waits for
    error: str | None = None


@dataclass(frozen=True)
class Process:
    """A key that doesn't apply is None, and the API leaves it out."""

    id: str
    module: str
    kind: str
    name: str
    state: ProcessState
    phase: str | None = None
    position: int | None = None
    strategies: tuple[str, ...] | None = None
    done: int | None = None
    total: int | None = None
    percent: int | None = None
    counters: Mapping[str, int] | None = None
    detail: str | None = None
    started: str | None = None
    finished: str | None = None
    elapsed_seconds: int | None = None  # alive: how long it has been running
    remaining_seconds: int | None = None  # alive and slow: how long it has left, at the pace so far
    duration_seconds: int | None = None  # ended: how long it took
    error: str | None = None


@dataclass(frozen=True)
class ProcessBoard:
    """How many there are in each state, and them: the alive ones first, then the last ones to end."""

    at: str
    counts: Mapping[ProcessState, int]
    processes: tuple[Process, ...]
    problems: tuple[str, ...] = ()  # what couldn't be read: the board may be behind


@dataclass(frozen=True)
class ProcessSnapshot:
    processes: tuple[Process, ...]
    problem: str | None = None


class ProcessSource(Protocol):
    def snapshot(self, at: datetime) -> ProcessSnapshot: ...
