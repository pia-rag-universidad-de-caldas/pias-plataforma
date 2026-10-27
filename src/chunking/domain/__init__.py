"""Chunking business rules: which documents are pending, how the document → sections → chunks hierarchy is built for
the graph and how a run goes (feature 023); the plan, parameters, record and run of experiments and their scores
(feature 025); promoting an approved experiment to the official graph (feature 028). They depend only on models
(ports and concepts) and config, never on HTTP nor on Docling.
"""

from .experiment_graph import ExperimentGraph
from .experiment_runner import ExperimentRunner
from .hierarchy import Hierarchy
from .parameters import InvalidParameters, Parameters
from .plan import Planner
from .promotion import Promotion
from .runner import FailureCallback, ProgressCallback, Runner
from .scoring import Scoring
from .selection import Selection

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
]
