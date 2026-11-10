"""What a process is, for every module (feature 039): its view and the board that gathers them. No domain and no web:
each module turns its own runs into `ProcessFacts`."""

from .history import History
from .models import ENDED, Process, ProcessBoard, ProcessFacts, ProcessSnapshot, ProcessSource, ProcessState
from .process_board import board
from .process_view import describe, seconds_between

__all__ = [
    "ENDED",
    "History",
    "Process",
    "ProcessBoard",
    "ProcessFacts",
    "ProcessSnapshot",
    "ProcessSource",
    "ProcessState",
    "board",
    "describe",
    "seconds_between",
]
