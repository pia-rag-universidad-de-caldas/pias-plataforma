"""Chunking business rules (feature 043). They depend only on models (ports and concepts) and config, never on HTTP
nor on docling-core.

- parameters.py: the configurable part resolved and checked, and the active configuration;
- experiments/: an experiment over some parsed documents, recorded apart from the official chunks;
- production/: POST /runs, chunking documents with the active configuration under their JSON;
- sections.py, stats.py, progress.py: what they share.
"""

from .experiments import Addition, ExperimentGraph, ExperimentRunner, Resolution
from .parameters import InvalidParameters, Parameters
from .production import OfficialGraph, RunGraph, RunRunner
from .sections import sections
from .stats import token_stats

__all__ = [
    "Addition",
    "ExperimentGraph",
    "ExperimentRunner",
    "InvalidParameters",
    "OfficialGraph",
    "Parameters",
    "Resolution",
    "RunGraph",
    "RunRunner",
    "sections",
    "token_stats",
]
