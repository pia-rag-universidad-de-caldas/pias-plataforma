"""The time of what the modules store and show (feature 040): always with its zone."""

from datetime import datetime


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
