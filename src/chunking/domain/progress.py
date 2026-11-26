"""The counters of an experiment or a run, moved forward."""

from dataclasses import replace

from chunking.models import ExperimentProgress, RunProgress


def advanced[P: (RunProgress, ExperimentProgress)](progress: P, **changes: int) -> P:
    """`progress` with each counter in `changes` increased by its value."""
    return replace(progress, **{name: getattr(progress, name) + value for name, value in changes.items()})
