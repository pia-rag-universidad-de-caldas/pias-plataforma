"""Chunking business rules. They depend only on models (ports and concepts) and config, never on HTTP nor on Docling.

- production/: which documents are pending, how the document → sections → chunks hierarchy is built for the graph
  and how a run goes (feature 023);
- experiments/: the plan, parameters, record and run of experiments and their scores (feature 025); promoting an
  approved experiment to the official graph (feature 028);
- progress.py: the counters both move forward.
"""

from .experiments import (
    ExperimentGraph,
    ExperimentRunner,
    InvalidParameters,
    Parameters,
    Planner,
    Promotion,
    Scoring,
    now,
)
from .production import FailureCallback, Hierarchy, ProgressCallback, Runner, Selection

__all__ = [
    "ExperimentGraph",
    "ExperimentRunner",
    "FailureCallback",
    "Hierarchy",
    "InvalidParameters",
    "Parameters",
    "Planner",
    "ProgressCallback",
    "Promotion",
    "Runner",
    "Scoring",
    "Selection",
    "now",
]
