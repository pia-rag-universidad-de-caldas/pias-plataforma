"""The counters of a run or an experiment, moved forward (shared by Runner and ExperimentRunner)."""

from dataclasses import replace

from chunking.models import ExperimentProgress, RunProgress


def advanced[P: (RunProgress, ExperimentProgress)](progress: P, **changes: int) -> P:
    """`progress` with each counter in `changes` increased by its value."""
    return replace(progress, **{name: getattr(progress, name) + value for name, value in changes.items()})
